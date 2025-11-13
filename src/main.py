import pygame, random, sys, math
pygame.init()

W, H = 600, 700
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

# === MODEL ===
class Segment:
    def __init__(self, id, length, speed_limit=13.9):
        self.id = id
        self.length = length
        self.speed_limit = speed_limit
        self.cars = []
        self.outputs = []  # for splitting

    def add_car(self, car, pos=0.0):
        car.segment = self
        car.pos = pos
        self.cars.append(car)

    def remove_car(self, car):
        if car in self.cars:
            self.cars.remove(car)

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

# === SEGMENTS ===
segments = {
    'north':  Segment('north',  200),
    'west':   Segment('west',   150),
    'east':   Segment('east',   150),
    'middle': Segment('middle', 100),
}

# Speed limits
for s in segments.values():
    s.speed_limit = V0

# === JUNCTIONS ===
# Split: north → west & east (round-robin)
segments['north'].outputs = [segments['west'], segments['east']]
split_counter = 0

# Merge: west & east → middle
# (Handled in transfer: both feed into middle)

# Loop back: middle → north
segments['middle'].outputs = [segments['north']]

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
    """Return (s, dv, leader_v) or (inf, 0, 0)"""
    if car_idx > 0:
        leader = seg.cars[car_idx - 1]
        s = leader.pos - seg.cars[car_idx].pos - leader.length
        dv = seg.cars[car_idx].v - leader.v
        return s, dv, leader.v
    return float('inf'), 0, 0

def update_cars(seg):
    if not seg.cars:
        return
    seg.cars.sort(key=lambda c: c.pos, reverse=True)

    for i, car in enumerate(seg.cars):
        v_free = min(car.v0, seg.speed_limit)
        s, dv, _ = get_leader(seg, i)
        a = idm_acceleration(car, s, dv, v_free)
        car.v = max(0, car.v + a * STEP)
        car.pos += car.v * STEP

        # Risk color
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

        if seg.outputs:  # Splitting or loop
            if seg.id == 'north':
                # Round-robin split
                output = seg.outputs[split_counter % len(seg.outputs)]
                split_counter += 1
            else:
                output = seg.outputs[0]
        else:
            # Merging into middle
            output = segments['middle']

        # Insert with gap
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
            if not segments['north'].cars or segments['north'].cars[-1].pos > 30:
                car = Car()
                segments['north'].add_car(car, 0)

    if spawn_timer > 1/spawn_rate:
        if not segments['north'].cars or segments['north'].cars[-1].pos > 30:
            car = Car()
            segments['north'].add_car(car, 0)
        spawn_timer = 0

    while accumulator >= STEP:
        for seg in segments.values():
            update_cars(seg)
        for seg in segments.values():
            transfer(seg)
        accumulator -= STEP

    # === RENDER ===
    screen.fill((30, 30, 30))

    # Coordinates
    cx, cy = W // 2, 150
    road_w = 20

    # Draw segments
    # North (vertical)
    pygame.draw.line(screen, (80,80,80), (cx, cy), (cx, cy + 200), road_w)
    # West (left arm)
    pygame.draw.line(screen, (80,80,80), (cx - 100, cy + 200), (cx - 250, cy + 200), road_w)
    # East (right arm)
    pygame.draw.line(screen, (80,80,80), (cx + 100, cy + 200), (cx + 250, cy + 200), road_w)
    # Middle (bottom)
    pygame.draw.line(screen, (80,80,80), (cx - 100, cy + 200), (cx + 100, cy + 200), road_w)
    # Merge lines
    pygame.draw.line(screen, (100,100,100), (cx - 250, cy + 200), (cx - 100, cy + 200), 4)
    pygame.draw.line(screen, (100,100,100), (cx + 250, cy + 200), (cx + 100, cy + 200), 4)

    # Labels
    labels = {
        'north': (cx, cy + 100),
        'west':  (cx - 175, cy + 180),
        'east':  (cx + 175, cy + 180),
        'middle':(cx, cy + 220),
    }
    for sid, (x, y) in labels.items():
        txt = font.render(sid, True, (200,200,200))
        screen.blit(txt, (x, y))

    # Draw cars
    color_map = {"green": (0,255,0), "yellow": (255,255,0), "red": (255,0,0)}
    all_cars = []

    for sid, seg in segments.items():
        for car in seg.cars:
            if sid == 'north':
                x = cx
                y = cy + car.pos
            elif sid == 'west':
                x = cx - 100 - (car.pos / 150) * 150
                y = cy + 200
            elif sid == 'east':
                x = cx + 100 + (car.pos / 150) * 150
                y = cy + 200
            elif sid == 'middle':
                t = car.pos / 100
                x = cx - 100 + t * 200
                y = cy + 200
            else:
                continue

            color = color_map[car.risk]
            pygame.draw.circle(screen, color, (int(x), int(y)), 9)
            if car.v > 2:
                pygame.draw.circle(screen, (255,255,255), (int(x), int(y)), 3)
            all_cars.append(car)

    # Stats
    if all_cars:
        avg_v = sum(c.v for c in all_cars) / len(all_cars)
        red = sum(1 for c in all_cars if c.risk == "red")
        txt = font.render(f'Avg: {avg_v:.1f} m/s | Cars: {len(all_cars)} | Red: {red}', True, (255,255,255))
        screen.blit(txt, (10, 10))

    pygame.display.flip()