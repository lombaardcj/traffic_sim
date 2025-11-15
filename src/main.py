import pygame, random, sys, math, json, os
pygame.init()

# === CONFIG LOADING ===
CONFIG_PATH = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'config.json')

def load_config():
    """Load configuration from config.json."""
    if not os.path.exists(CONFIG_PATH):
        print(f"Config file not found at {CONFIG_PATH}")
        return None
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def save_config(config):
    """Save configuration to config.json."""
    with open(CONFIG_PATH, 'w') as f:
        json.dump(config, f, indent=2)

def update_config_current_state(config):
    """Update current_state with zoom/pan and segment config."""
    global ZOOM, PAN_X, PAN_Y, segments, junctions, POINTS
    
    config['current_state']['view']['zoom'] = ZOOM
    config['current_state']['view']['pan_x'] = PAN_X
    config['current_state']['view']['pan_y'] = PAN_Y
    
    # Update segments
    for seg_data in config['current_state']['segments']:
        if seg_data['id'] in segments:
            seg = segments[seg_data['id']]
            seg_data['start'] = list(seg.start)
            seg_data['end'] = list(seg.end)
            seg_data['speed_limit'] = seg.speed_limit
    
    # Update junctions
    for j_idx, j_data in enumerate(config['current_state']['junctions']):
        if j_idx < len(junctions):
            j = junctions[j_idx]
            j_data['mode'] = j.mode

def reset_to_default_state(config):
    """Reset current state to default state."""
    global ZOOM, PAN_X, PAN_Y, segments, junctions, POINTS
    
    default = config['default_state']
    
    # Reset view
    ZOOM = default['view']['zoom']
    PAN_X = default['view']['pan_x']
    PAN_Y = default['view']['pan_y']
    
    # Reset POINTS
    for key, val in default['points'].items():
        POINTS[key] = tuple(val)
    
    # Clear and reset segments
    for seg in segments.values():
        seg.cars = []
    
    # Reset segment positions
    for seg_data in default['segments']:
        if seg_data['id'] in segments:
            seg = segments[seg_data['id']]
            seg.start = tuple(seg_data['start'])
            seg.end = tuple(seg_data['end'])
            seg.speed_limit = seg_data['speed_limit']
            # Recalculate length and direction
            dx = seg.end[0] - seg.start[0]
            dy = seg.end[1] - seg.start[1]
            seg.length = math.hypot(dx, dy)
            seg.dir = (dx / seg.length, dy / seg.length) if seg.length > 0 else (0, 0)
    
    # Reset junctions
    for j in junctions:
        j.counter = 0

# Load config on startup
config = load_config()
if config is None:
    print("Failed to load config. Please ensure config.json exists.")
    sys.exit(1)

# === SCREEN ===
W, H = 700, 700
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)

# === VIEW / ZOOM / PAN ===
ZOOM = 1.0           # global zoom (1.0 = 100%)
MIN_ZOOM = 0.2
MAX_ZOOM = 5.0
PAN_X, PAN_Y = 0.0, 0.0   # translation in screen pixels
is_panning = False
pan_last = (0, 0)

def world_to_screen(pt):
    """Convert world coordinates (same units as your POINTS) to screen coords."""
    x, y = pt
    sx = x * ZOOM + PAN_X
    sy = y * ZOOM + PAN_Y
    return (int(sx), int(sy))

def screen_to_world(pt):
    """Convert screen coords to world coordinates (useful for zoom centering)."""
    sx, sy = pt
    wx = (sx - PAN_X) / ZOOM
    wy = (sy - PAN_Y) / ZOOM
    return (wx, wy)

def zoom_at(point_screen, factor):
    """Zoom in/out keeping the world point under `point_screen` stable."""
    global ZOOM, PAN_X, PAN_Y
    # clamp target zoom
    new_zoom = max(MIN_ZOOM, min(MAX_ZOOM, ZOOM * factor))
    if new_zoom == ZOOM:
        return
    # world point under the cursor before zoom
    world = screen_to_world(point_screen)
    # update zoom
    ZOOM = new_zoom
    # compute new pan so that the same world point maps to same screen point
    PAN_X = point_screen[0] - world[0] * ZOOM
    PAN_Y = point_screen[1] - world[1] * ZOOM

# === LOAD INITIAL VIEW STATE FROM CONFIG ===
if config:
    ZOOM = config['current_state']['view']['zoom']
    PAN_X = config['current_state']['view']['pan_x']
    PAN_Y = config['current_state']['view']['pan_y']

# === IDM PARAMETERS (Intelligent Driver Model) ===
# All values based on real-world traffic studies (NGSIM, HighD, Treiber et al.)
# Units: meters (m), seconds (s), meters per second (m/s), m/s²

# A_MAX = 2.0
A_MAX = 3.0
# Maximum comfortable acceleration
# Unit: m/s²
# Meaning: How quickly a driver can speed up when unobstructed
# Typical: 1.0–3.0 m/s² (human drivers), 3.0–5.0 for aggressive or AVs
# Effect: ↑ = faster starts, smoother flow | ↓ = sluggish response

B_MAX = 4.0
# Maximum comfortable deceleration (braking)
# Unit: m/s²
# Meaning: How hard a driver brakes in normal conditions (not emergency)
# Typical: 2.0–4.0 m/s² (humans), up to 8.0 in panic
# Effect: ↑ = stronger reaction to gaps → more shockwaves | ↓ = gentler, less jam-prone

# V0 = 13.9
V0 = 33.3
# Desired free-flow speed (cruise speed when no leader)
# Unit: m/s
# 13.9 m/s = 50 km/h ≈ 31 mph
# Typical: 13.9–33.3 m/s (50–120 km/h) depending on road type
# Effect: ↑ = higher capacity | Must match speed_limit or be capped

T = 1.8
# Safe time headway
# Unit: seconds
# Meaning: Minimum time gap to the car in front at current speed
# Example: at 10 m/s, wants 15 m gap
# Typical: 1.0–1.8 s (1.5 is standard for highways)
# Effect: ↑ = lower density, fewer jams | ↓ = denser flow, more red cars

S0 = 3.0
# Minimum jam distance (standstill gap)
# Unit: meters
# Meaning: Extra buffer when stopped (beyond car length)
# Includes: reaction slack, bumper margin
# Typical: 1.5–3.0 m
# Effect: ↑ = lower jam density (~120 veh/km) | ↓ = denser jams (~200 veh/km)

CAR_LENGTH = 4.5
# Physical length of a car
# Unit: meters
# Standard passenger car: 4.5–5.0 m
# Used in gap calculation: s = leader.pos - follower.pos - CAR_LENGTH
# Do not include in S0 — S0 is *extra* gap

MARGIN = 4.0
# Risk visualization buffer
# Unit: meters
# Meaning: How much beyond s* triggers YELLOW (not part of IDM physics)
# Purely for coloring: green → yellow → red
# Typical: 2.0–6.0 m
# Effect: ↑ = fewer yellows | ↓ = more sensitive warning

STEP = 0.05
# Simulation timestep
# Unit: seconds
# Meaning: How often physics is updated
# 0.05 s = 20 Hz update rate
# Must be small for stability (especially with high A_MAX)
# Typical: 0.01–0.1 s
# Warning: Too large → oscillation or crash | Too small → slow sim

ROAD_WIDTH = 40
# Visual road thickness in pixels
# Unit: pixels
# Purely cosmetic — for pygame.draw.line()
# Adjust to match screen scale (40px ≈ 3.5–4.0 m lane width visually)
# No effect on physics

# === HELPER POINTS (easy to edit) ===
POINTS = {
    'north_start': (350, 100),
    'north_end':   (350, 300),
    'split':       (350, 300),
    'west_start':  (350, 300),
    'west_end':    (100, 300),
    'east_start':  (350, 300),
    'east_end':    (600, 300),
}

# === SEGMENT CLASS ===
class Segment:
    def __init__(self, id, start_pt, end_pt, speed_limit=13.9):
        self.id = id
        self.start = start_pt
        self.end = end_pt
        self.speed_limit = speed_limit
        self.cars = []
        self.outputs = []  # for splitting

        # Precompute
        dx = end_pt[0] - start_pt[0]
        dy = end_pt[1] - start_pt[1]
        self.length = math.hypot(dx, dy)
        self.dir = (dx / self.length, dy / self.length) if self.length > 0 else (0, 0)

    def add_car(self, car, pos=0.0):
        car.segment = self
        car.pos = pos
        self.cars.append(car)

    def remove_car(self, car):
        if car in self.cars:
            self.cars.remove(car)

    # === DRAW ROAD ===
    def draw_road(self, surface, color=(80,80,80)):
        if self.length == 0:
            return
        p1 = world_to_screen(self.start)
        p2 = world_to_screen(self.end)
        # Scale road width with zoom
        rw = max(1, int(ROAD_WIDTH * ZOOM))
        pygame.draw.line(surface, color, p1, p2, rw)

    # === DRAW CARS ===
    def draw_cars(self, surface):
        if self.length <= 0:
            return

        # === SEGMENT LENGTH IN SCREEN PIXELS ===
        s1 = world_to_screen(self.start)
        s2 = world_to_screen(self.end)
        seg_pixels = math.hypot(s2[0] - s1[0], s2[1] - s1[1])
        # pixels per meter (based on world meters length)
        ppm = (seg_pixels / self.length) if self.length > 0 else 1.0

        # Car dimensions (in screen pixels)
        car_pixel_length = max(4, CAR_LENGTH * ppm)
        car_pixel_width = max(2, 2.0 * ppm)
        half_len = car_pixel_length / 2.0
        half_w = car_pixel_width / 2.0

        color_map = {
            "green": (0, 255, 0),
            "yellow": (255, 255, 0),
            "red": (255, 0, 0),
        }

        for car in self.cars:
            t = car.pos / self.length if self.length > 0 else 0.0
            # world position along segment (in world coords)
            x = self.start[0] + t * (self.end[0] - self.start[0])
            y = self.start[1] + t * (self.end[1] - self.start[1])
            # transform to screen
            sx, sy = world_to_screen((x, y))

            # Direction (angle) uses screen direction to remain visually correct
            dx = s2[0] - s1[0]
            dy = s2[1] - s1[1]
            angle = math.atan2(dy, dx)
            cos_a, sin_a = math.cos(angle), math.sin(angle)

            # CAR BODY corners in screen-space relative coords
            corners = [
                (-half_len, -half_w),
                ( half_len, -half_w),
                ( half_len,  half_w),
                (-half_len,  half_w),
            ]
            rotated = []
            for px, py in corners:
                rx = px * cos_a - py * sin_a + sx
                ry = px * sin_a + py * cos_a + sy
                rotated.append((int(round(rx)), int(round(ry))))

            color = (180, 0, 255) if getattr(car, 'colliding', False) else color_map[car.risk]
            pygame.draw.polygon(surface, color, rotated)

            # HEADLIGHT / BEAM (scaled)
            if car.v > 2.0:
                # Headlight origin (front center)
                front_x = sx + half_len * cos_a
                front_y = sy + half_len * sin_a

                # Beam parameters
                beam_length_m = 6.0 + car.v * 0.6  # 6–15m
                beam_angle = 0.4  # radians (~23°)
                steps = 8  # fade steps

                beam_pixels = beam_length_m * ppm

                for i in range(steps):
                    # Fade: 200 → 50 alpha
                    alpha = int(200 * (1 - i / steps))
                    color = (255, 240, 180, alpha)

                    # Cone width at this step
                    dist = (i + 1) / steps * beam_pixels
                    width = 2 * dist * math.tan(beam_angle)

                    # Create triangle points
                    p1 = (front_x, front_y)  # origin
                    p2 = (
                        front_x + dist * cos_a - width * sin_a,
                        front_y + dist * sin_a + width * cos_a
                    )
                    p3 = (
                        front_x + dist * cos_a + width * sin_a,
                        front_y + dist * sin_a - width * cos_a
                    )

                    # Draw translucent triangle
                    tri_surf = pygame.Surface((W, H), pygame.SRCALPHA)
                    pygame.draw.polygon(tri_surf, color, [p1, p2, p3])
                    surface.blit(tri_surf, (0, 0))

# === CAR CLASS ===
class Car:
    def __init__(self):
        self.pos = 0.0
        self.v = 0.0
        self.segment = None
        self.length = CAR_LENGTH
        self.v0 = V0
        self.a_max = A_MAX
        self.b_max = B_MAX
        self.T = T
        self.s0 = S0
        self.risk = "green"
        self.colliding = False

# === JUNCTION ===
class Junction:
    def __init__(self, id, inputs, outputs, mode="round_robin"):
        self.id = id
        self.inputs = inputs if isinstance(inputs, list) else [inputs]  # 1 or N
        self.outputs = outputs if isinstance(outputs, list) else [outputs]
        self.mode = mode
        self.counter = 0  # for round-robin

    # === DRAW JUNCTIONS
    def draw_junction(self, surface, road_width=ROAD_WIDTH):
        """
        Draw the junction as:
        - Square border (on top of road)
        - Circle with cross (X) in center
        - Below cars, above roads
        """
        # Get junction position: average of input segment ends
        end_points = []
        for inp in (self.inputs if isinstance(self.inputs, list) else [self.inputs]):
            end_points.append((inp.end[0], inp.end[1]))

        if not end_points:
            return

        # Center of selfunction
        cx = sum(p[0] for p in end_points) // len(end_points)
        cy = sum(p[1] for p in end_points) // len(end_points)

        size = road_width * 1.3  # slightly larger than road
        half = size // 2

        # Transform rect center
        top_left = world_to_screen((cx - half, cy - half))
        rect_w = int(size * ZOOM)
        rect_h = int(size * ZOOM)
        rect = pygame.Rect(top_left[0], top_left[1], rect_w, rect_h)
        pygame.draw.rect(surface, (255, 255, 255), rect, max(1, int(4 * ZOOM)))

        # Circle center in screen coords
        center = world_to_screen((cx, cy))
        radius = int(size * 0.4 * ZOOM)
        if radius > 0:
            pygame.draw.circle(surface, (100, 100, 100), center, radius)

            line_len = radius * 0.8
            pygame.draw.line(surface, (200, 200, 200),
                            (center[0] - line_len, center[1] - line_len),
                            (center[0] + line_len, center[1] + line_len), max(1, int(3 * ZOOM)))
            pygame.draw.line(surface, (200, 200, 200),
                            (center[0] + line_len, center[1] - line_len),
                            (center[0] - line_len, center[1] + line_len), max(1, int(3 * ZOOM)))


# === CREATE SEGMENTS USING POINTS ===
segments = {
    'northsouth':   Segment('northsouth',  POINTS['north_start'], POINTS['north_end']),
    'west'      :   Segment('west',        POINTS['west_start'],  POINTS['west_end']),
    'east'      :   Segment('east',        POINTS['east_start'],  POINTS['east_end']),
    'eastnorth' :   Segment('eastnorth',   POINTS['east_end'],  POINTS['north_start']),
    'westnorth' :   Segment('westnorth',   POINTS['west_end'],  POINTS['north_start']),
}

# === JUNCTIONS LIST ===
junctions = [
    # Split: northsouth → west & east
    Junction('split', 
             inputs=segments['northsouth'], 
             outputs=[segments['west'], segments['east']], 
             mode="round_robin"),

    # Merge: west + east → eastnorth + westLectnorth
    Junction('westaround', 
             inputs=[segments['west']], 
             outputs=[segments['westnorth']], 
             mode="priority"),

    Junction('eastaround', 
             inputs=[segments['east']], 
             outputs=[segments['eastnorth']], 
             mode="priority"),

    # Loop back: eastnorth + westnorth → northsouth
    Junction('merge', 
             inputs=[segments['eastnorth'], segments['westnorth']], 
             outputs=segments['northsouth'], 
             mode="priority"),
]

# Junction logic
def transfer_at_junction(junction):
    """Move cars from inputs to outputs — only if safe at start of output."""
    for input_seg in junction.inputs:
        exiting = [c for c in input_seg.cars if c.pos >= input_seg.length]
        for car in exiting:
            input_seg.remove_car(car)

            # === Choose output ===
            if junction.mode == "round_robin":
                output = junction.outputs[junction.counter % len(junction.outputs)]
                junction.counter += 1
            elif junction.mode in ["priority", "fixed"]:
                output = junction.outputs[0]
            else:
                output = random.choice(junction.outputs)

            # === Insert safely at pos=0 ===
            entry = 0
            if output.cars:
                first_car = min(output.cars, key=lambda c: c.pos)
                min_gap = car.length + first_car.length + car.s0
                if first_car.pos < min_gap:
                    # Not safe — push back and wait
                    input_seg.add_car(car, input_seg.length - 0.1)
                    continue
            # Safe — enter at 0
            output.add_car(car, entry)
            car.v = min(car.v, output.speed_limit)

# === IDM ===
def idm_acceleration(car, s, dv, v_free):
    if s <= 0:
        return -car.b_max
    v_ratio = car.v / v_free
    s_star = car.s0 + max(0, car.v * car.T + (car.v * dv) / (2 * math.sqrt(car.a_max * car.b_max)))
    interaction = (s_star / s) ** 2 if s > 0 else 10.0
    a = car.a_max * (1 - v_ratio**4 - interaction)
    return max(-car.b_max, min(car.a_max, a))

def get_leader(seg, car_idx):
    """
    Return (s, dv) to the *closest* downstream leader.
    - Same segment: immediate
    - Downstream: check ALL output paths → pick nearest car
    """
    car = seg.cars[car_idx]

    # 1. Local leader
    if car_idx > 0:
        leader = seg.cars[car_idx - 1]
        s = leader.pos - car.pos - leader.length
        dv = car.v - leader.v
        return s, dv

    # 2. Look ahead through junctions
    best_s = float('inf')
    best_dv = 0

    visited = set()
    queue = [(seg, seg.length)]  # (current_seg, dist_from_ego)

    while queue:
        current_seg, dist_offset = queue.pop(0)
        if current_seg.id in visited:
            continue
        visited.add(current_seg.id)

        # Check cars in this segment
        if current_seg.cars:
            rear_car = min(current_seg.cars, key=lambda c: c.pos)
            s = dist_offset + rear_car.pos - car.pos - rear_car.length
            dv = car.v - rear_car.v
            if s < best_s:
                best_s = s
                best_dv = dv

        # Enqueue outputs
        outputs = []
        if hasattr(current_seg, 'outputs') and current_seg.outputs:
            outputs = current_seg.outputs
        elif hasattr(current_seg, 'next_segment') and current_seg.next_segment:
            outputs = [current_seg.next_segment]

        for out_seg in outputs:
            if out_seg.id not in visited:
                queue.append((out_seg, dist_offset + out_seg.length))

    return (best_s, best_dv) if best_s != float('inf') else (float('inf'), 0)

def update_cars(seg):
    if not seg.cars:
        return
    seg.cars.sort(key=lambda c: c.pos, reverse=True)  # front to back

    for i, car in enumerate(seg.cars):
        v_free = min(car.v0, seg.speed_limit)
        s, dv = get_leader(seg, i)
        a = idm_acceleration(car, s, dv, v_free)
        car.v = max(0, car.v + a * STEP)
        car.pos += car.v * STEP

        # === COLLISION DETECTION ===
        car.colliding = False  # reset
        if i > 0:
            leader = seg.cars[i-1]
            # Actual front-to-back gap
            actual_gap = leader.pos - car.pos - leader.length
            if actual_gap < 0:  # overlap!
                car.colliding = True
                leader.colliding = True  # both cars purple

        # === RISK COLORING (unchanged) ===
        if s == float('inf'):
            car.risk = "green"
        else:
            s_star = car.s0 + max(0, car.v * car.T + (car.v * dv) / (2 * math.sqrt(car.a_max * car.b_max)))
            if s <= s_star:
                car.risk = "red"
            elif s <= s_star + MARGIN:
                car.risk = "yellow"
            else:
                car.risk = "green"

            

def transfer(seg):
    global split_counter
    exiting = [c for c in seg.cars if c.pos >= seg.length]
    for car in exiting:
        seg.remove_car(car)

        if seg.outputs:
            if seg.id == 'north':
                output = seg.outputs[split_counter % len(seg.outputs)]
                split_counter += 1
            else:
                output = seg.outputs[0]
        else:
            output = segments['middle']

        entry = 0
        if output.cars:
            rear = min(output.cars, key=lambda c: c.pos)
            entry = max(0, rear.pos - car.length - car.s0)
        output.add_car(car, entry)
        car.v = min(car.v, output.speed_limit)

# === SPAWN ===
spawn_rate = 0.8
spawn_timer = 0

# === MAIN LOOP ===
accumulator = 0
while True:
    dt = clock.tick(60) / 1000.0
    accumulator += dt
    spawn_timer += dt

    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            sys.exit()
        
        # === ZOOM ===
        if e.type == pygame.MOUSEBUTTONDOWN:
            if e.button == 4:  # scroll up (zoom in)
                zoom_at(pygame.mouse.get_pos(), 1.1)
            elif e.button == 5:  # scroll down (zoom out)
                zoom_at(pygame.mouse.get_pos(), 0.9)
        
        # === PANNING ===
        if e.type == pygame.MOUSEBUTTONDOWN and e.button == 3:  # right-click
            is_panning = True
            pan_last = pygame.mouse.get_pos()
        if e.type == pygame.MOUSEBUTTONUP and e.button == 3:
            is_panning = False
        if e.type == pygame.MOUSEMOTION and is_panning:
            mouse = pygame.mouse.get_pos()
            dx = mouse[0] - pan_last[0]
            dy = mouse[1] - pan_last[1]
            PAN_X += dx
            PAN_Y += dy
            pan_last = mouse
        
        if e.type == pygame.KEYDOWN:
            # === PLUS/MINUS ZOOM ===
            if e.key == pygame.K_PLUS or e.key == pygame.K_EQUALS:
                zoom_at(pygame.mouse.get_pos(), 1.1)
            elif e.key == pygame.K_MINUS:
                zoom_at(pygame.mouse.get_pos(), 0.9)
            
            # === SPAWN CAR ===
            if e.key == pygame.K_SPACE:
                north = segments['northsouth']
                if not north.cars or north.cars[-1].pos > 30:
                    car = Car()
                    north.add_car(car, 0)
            
            # === SAVE CONFIG (Ctrl+S) ===
            if e.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                update_config_current_state(config)
                save_config(config)
                print("Config saved to config.json")
            
            # === RESET TO DEFAULT (R key) ===
            if e.key == pygame.K_r:
                reset_to_default_state(config)
                print("Reset to default state")

    if spawn_timer > 1/spawn_rate:
        north = segments['northsouth']
        if not north.cars or north.cars[-1].pos > 30:
            car = Car()
            north.add_car(car, 0)
        spawn_timer = 0

    while accumulator >= STEP:
        for seg in segments.values():
            update_cars(seg)

        # === TRANSFER VIA JUNCTIONS ===
        for j in junctions:
            transfer_at_junction(j)
        
        accumulator -= STEP

    # === RENDER ===
    screen.fill((30, 30, 30))

    # Draw all roads
    for seg in segments.values():
        seg.draw_road(screen)

    # Draw all junctions
    for junc in junctions:
        junc.draw_junction(screen)

    # Draw all cars
    for seg in segments.values():
        seg.draw_cars(screen)

    # Labels
    label_pos = {
        'north':  POINTS['north_start'],
        'west':   POINTS['west_end'],
        'east':   POINTS['east_end'],
    }
    for sid, (x, y) in label_pos.items():
        txt = font.render(sid, True, (200,200,200))
        screen.blit(txt, (x, y))

    # Stats
    all_cars = [c for seg in segments.values() for c in seg.cars]
    if all_cars:
        avg_v = sum(c.v for c in all_cars) / len(all_cars)
        red = sum(1 for c in all_cars if c.risk == "red")
        txt = font.render(f'Avg: {avg_v:.1f} m/s | Cars: {len(all_cars)} | Red: {red}', True, (255,255,255))
        screen.blit(txt, (10, 10))

    pygame.display.flip()
