import pygame, random, sys, math
pygame.init()

# === SCREEN ===
W, H = 700, 700
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)

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
        pygame.draw.line(surface, color, self.start, self.end, ROAD_WIDTH)

    # === DRAW CARS ===
    def draw_cars(self, surface):
        color_map = {"green": (0,255,0), "yellow": (255,255,0), "red": (255,0,0)}
        for car in self.cars:
            t = car.pos / self.length
            x = self.start[0] + t * (self.end[0] - self.start[0])
            y = self.start[1] + t * (self.end[1] - self.start[1])
            color = color_map[car.risk]
            pygame.draw.circle(surface, color, (int(x), int(y)), 9)
            if car.v > 2:
                pygame.draw.circle(surface, (255,255,255), (int(x), int(y)), 3)

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

# === JUNCTION ===
class Junction:
    def __init__(self, id, inputs, outputs, mode="round_robin"):
        self.id = id
        self.inputs = inputs if isinstance(inputs, list) else [inputs]  # 1 or N
        self.outputs = outputs if isinstance(outputs, list) else [outputs]
        self.mode = mode
        self.counter = 0  # for round-robin

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
    seg.cars.sort(key=lambda c: c.pos, reverse=True)
    for i, car in enumerate(seg.cars):
        v_free = min(car.v0, seg.speed_limit)
        s, dv = get_leader(seg, i)
        a = idm_acceleration(car, s, dv, v_free)
        car.v = max(0, car.v + a * STEP)
        car.pos += car.v * STEP

        # Risk
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
        if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
            north = segments['northsouth']
            if not north.cars or north.cars[-1].pos > 30:
                car = Car()
                north.add_car(car, 0)

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
