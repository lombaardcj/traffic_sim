import pygame, random, sys
import math
pygame.init()

W, H = 500, 500
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)

# === IDM PARAMETERS ===
A_MAX = 2.0      # m/s²
B_MAX = 3.0      # m/s²
V0 = 13.9        # desired speed (50 km/h)
T = 1.5          # safe time headway (s)
S0 = 2.0         # min jam distance (m)
CAR_LENGTH = 4.5
MARGIN = 4.0     # for yellow zone

# === MODEL ===
class Segment:
    def __init__(self, id, length, speed_limit=13.9):
        self.id = id
        self.length = length
        self.speed_limit = speed_limit
        self.cars = []
        self.next_segment = None

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
        self.v = 0.0           # current speed
        self.segment = None
        self.length = CAR_LENGTH
        self.v0 = V0
        self.a_max = A_MAX
        self.b_max = B_MAX
        self.T = T
        self.s0 = S0
        self.risk = "green"    # green, yellow, red

# === WORLD ===
segments = {
    'north': Segment('north', 200),
    'east':  Segment('east',  200),
    'south': Segment('south', 200),
    'west':  Segment('west',  200),
}
for s in segments.values():
    s.speed_limit = V0

# Connect in loop
segments['north'].next_segment = segments['east']
segments['east'].next_segment  = segments['south']
segments['south'].next_segment = segments['west']
segments['west'].next_segment  = segments['north']

# === IDM UPDATE ===
def idm_acceleration(car, s, dv, v_free):
    if s <= 0:
        return -car.b_max  # emergency

    v_ratio = car.v / v_free
    s_star = car.s0 + max(0, car.v * car.T + (car.v * dv) / (2 * math.sqrt(car.a_max * car.b_max)))
    interaction = (s_star / s) ** 2 if s > 0 else 10.0
    a = car.a_max * (1 - v_ratio**4 - interaction)
    return max(-car.b_max, min(car.a_max, a))

def update_cars(seg):
    if not seg.cars:
        return
    seg.cars.sort(key=lambda c: c.pos, reverse=True)  # front to back

    for i, car in enumerate(seg.cars):
        v_free = min(car.v0, seg.speed_limit)

        if i > 0:
            leader = seg.cars[i-1]
            s = leader.pos - car.pos - leader.length
            dv = car.v - leader.v  # closing → positive
        else:
            s = float('inf')
            dv = 0

        a = idm_acceleration(car, s, dv, v_free)
        car.v = max(0, car.v + a * STEP)
        car.pos += car.v * STEP

        # === RISK COLORING ===
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
    exiting = [c for c in seg.cars if c.pos >= seg.length]
    for car in exiting:
        seg.remove_car(car)
        next_seg = seg.next_segment
        entry = 0
        if next_seg.cars:
            last = min(next_seg.cars, key=lambda c: c.pos)
            entry = max(0, last.pos - car.length - car.s0)
        next_seg.add_car(car, entry)
        car.v = min(car.v, next_seg.speed_limit)  # respect new limit

# === SIMULATION ===
STEP = 0.05
accumulator = 0
spawn_rate = 0.6
spawn_timer = 0

# === MAIN LOOP ===
while True:
    dt = clock.tick(60) / 1000.0
    accumulator += dt
    spawn_timer += dt

    for e in pygame.event.get():
        if e.type == pygame.QUIT:
            sys.exit()
        if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
            seg = random.choice(list(segments.values()))
            if not seg.cars or seg.cars[-1].pos > 25:
                car = Car()
                seg.add_car(car, 0)

    if spawn_timer > 1/spawn_rate:
        seg = random.choice(list(segments.values()))
        if not seg.cars or seg.cars[-1].pos > 25:
            car = Car()
            seg.add_car(car, 0)
        spawn_timer = 0

    while accumulator >= STEP:
        for seg in segments.values():
            update_cars(seg)
        for seg in segments.values():
            transfer(seg)
        accumulator -= STEP

    # === RENDER ===
    screen.fill((30, 30, 30))
    ox, oy, size = 100, 100, 200

    draws = {
        'north': ((ox, oy), (ox + size, oy)),
        'east':  ((ox + size, oy), (ox + size, oy + size)),
        'south': ((ox + size, oy + size), (ox, oy + size)),
        'west':  ((ox, oy + size), (ox, oy)),
    }

    # Draw roads
    for (p1, p2) in draws.values():
        pygame.draw.line(screen, (80, 80, 80), p1, p2, 40)

    # Draw cars with risk color
    color_map = {
        "green": (0, 255, 0),
        "yellow": (255, 255, 0),
        "red": (255, 0, 0)
    }

    all_cars = []
    for sid, (p1, p2) in draws.items():
        seg = segments[sid]
        for car in seg.cars:
            t = min(car.pos / seg.length, 1.0)
            x = p1[0] + t * (p2[0] - p1[0])
            y = p1[1] + t * (p2[1] - p1[1])
            color = color_map[car.risk]
            pygame.draw.circle(screen, color, (int(x), int(y)), 9)
            # Draw speed indicator
            if car.v > 0:
                pygame.draw.circle(screen, (255, 255, 255), (int(x), int(y)), 3)

            all_cars.append(car)

    # Stats
    if all_cars:
        avg_v = sum(c.v for c in all_cars) / len(all_cars)
        red_count = sum(1 for c in all_cars if c.risk == "red")
        txt = font.render(f'Avg: {avg_v:.1f} m/s | Cars: {len(all_cars)} | Red: {red_count}', True, (255,255,255))
        screen.blit(txt, (10, 10))

    pygame.display.flip()
