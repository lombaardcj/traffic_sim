import pygame, random, sys, math
pygame.init()

# === SCREEN ===
W, H = 700, 700
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)

# === IDM PARAMETERS ===
A_MAX = 2.0
B_MAX = 3.0
V0 = 13.9
T = 1.5
S0 = 2.0
CAR_LENGTH = 4.5
MARGIN = 4.0
STEP = 0.05
ROAD_WIDTH = 40

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
    def __init__(self, input_seg, output_segs, mode="round_robin"):
        self.inputs = input_seg
        self.outputs = output_segs
        self.mode = mode #round_robin
        self.counter = 0  # for round-robin

# === CREATE SEGMENTS USING POINTS ===
segments = {
    'northsouth':   Segment('northsouth',  POINTS['north_start'], POINTS['north_end']),
    'west'      :   Segment('west',        POINTS['west_start'],  POINTS['west_end']),
    'east'      :   Segment('east',        POINTS['east_start'],  POINTS['east_end']),
    'eastnorth' :   Segment('eastnorth',   POINTS['east_end'],  POINTS['north_start']),
    'westnorth' :   Segment('westnorth',   POINTS['west_end'],  POINTS['north_start']),
}

# Example: Heart shape
split_junction = Junction(
    input_seg=segments['northsouth'],
    output_segs=[segments['west'], segments['east']],
    mode="round_robin"
)

merge_junction = Junction(
    input_seg=None,  # not used
    output_segs=[segments['middle']],
    mode="priority"
)

# For merging: call transfer on each input
west_to_middle = Junction(segments['west'], [segments['middle']])
east_to_middle = Junction(segments['east'], [segments['middle']])

# === JUNCTIONS ===
# Split: north → west & east
segments['northsouth'].outputs = [segments['west'], segments['east']]
split_counter = 0

# Merge: west & east → middle
# (Handled in transfer)

# Loop: middle → north
segments['east'].outputs = [segments['eastnorth']]
segments['eastnorth'].outputs = [segments['northsouth']]

segments['west'].outputs = [segments['westnorth']]
segments['westnorth'].outputs = [segments['northsouth']]

# Junction logic
def transfer_at_junction(junction):
    """Move cars from input to outputs when they reach end."""
    input_seg = junction.input
    exiting = [c for c in input_seg.cars if c.pos >= input_seg.length]

    for car in exiting:
        input_seg.remove_car(car)

        # === Choose output ===
        if junction.mode == "round_robin":
            output = junction.outputs[junction.counter % len(junction.outputs)]
            junction.counter += 1
        elif junction.mode == "priority":
            output = junction.outputs[0]  # first has priority
        elif junction.mode == "random":
            output = random.choice(junction.outputs)
        else:
            output = junction.outputs[0]

        # === Insert safely ===
        entry = 0
        if output.cars:
            rear = min(output.cars, key=lambda c: c.pos)
            entry = max(0, rear.pos - car.length - car.s0)

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
    if car_idx > 0:
        leader = seg.cars[car_idx - 1]
        s = leader.pos - seg.cars[car_idx].pos - leader.length
        dv = seg.cars[car_idx].v - leader.v
        return s, dv
    return float('inf'), 0

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
        for seg in segments.values():
            transfer(seg)
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
