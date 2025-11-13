import pygame, random, sys
pygame.init()

W, H = 500, 500
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)

# === MODEL ===
class Segment:
    def __init__(self, id, length, speed_limit=13.9):
        self.id, self.length, self.speed_limit = id, length, speed_limit
        self.cars = []
        self.next_segment = None
    def add_car(self, car, pos=0):
        car.segment = self; car.pos = pos; self.cars.append(car)
    def remove_car(self, car): self.cars.remove(car)

class Car:
    def __init__(self):
        self.pos = 0.0
        self.segment = None
        self.length = 4.5
        self.min_gap = 2.0
        self.target_speed = 0.0

# === WORLD ===
segments = {
    'north': Segment('north', 200),
    'east':  Segment('east',  200),
    'south': Segment('south', 200),
    'west':  Segment('west',  200),
}
for s in segments.values(): s.speed_limit = 13.9

# Connect in loop (right turns)
segments['north'].next_segment = segments['east']
segments['east'].next_segment  = segments['south']
segments['south'].next_segment = segments['west']
segments['west'].next_segment  = segments['north']

# === SIMULATION ===
dt = 0
accumulator = 0
STEP = 0.05
spawn_rate = 0.6
spawn_timer = 0

def update_cars(seg):
    if not seg.cars: return
    seg.cars.sort(key=lambda c: c.pos, reverse=True)
    for i, car in enumerate(seg.cars):
        leader_pos = seg.cars[i-1].pos if i > 0 else float('inf')
        gap = leader_pos - car.pos - (seg.cars[i-1].length if i > 0 else 0)
        safe = float('inf') if gap > car.min_gap else 0
        car.target_speed = min(seg.speed_limit, safe)
        car.pos += car.target_speed * STEP

def transfer(seg):
    exiting = [c for c in seg.cars if c.pos >= seg.length]
    for car in exiting:
        seg.remove_car(car)
        next_seg = seg.next_segment
        entry = 0
        if next_seg.cars:
            last = min(next_seg.cars, key=lambda c: c.pos)
            entry = max(0, last.pos - car.length - car.min_gap)
        next_seg.add_car(car, entry)

# === MAIN LOOP ===
while True:
    dt = clock.tick(60) / 1000.0
    accumulator += dt
    spawn_timer += dt

    for e in pygame.event.get():
        if e.type == pygame.QUIT: sys.exit()
        if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE:
            seg = random.choice(list(segments.values()))
            if not seg.cars or seg.cars[-1].pos > 20:
                seg.add_car(Car(), 0)

    if spawn_timer > 1/spawn_rate:
        seg = random.choice(list(segments.values()))
        if not seg.cars or seg.cars[-1].pos > 20:
            seg.add_car(Car(), 0)
        spawn_timer = 0

    while accumulator >= STEP:
        for seg in segments.values():
            update_cars(seg)
        for seg in segments.values():
            transfer(seg)
        accumulator -= STEP

    # === RENDER ===
    screen.fill((30,30,30))
    ox, oy, size = 100, 100, 200

    draws = {
        'north': ((ox, oy), (ox + size, oy)),
        'east':  ((ox + size, oy), (ox + size, oy + size)),
        'south': ((ox + size, oy + size), (ox, oy + size)),
        'west':  ((ox, oy + size), (ox, oy)),
    }

    for sid, (p1, p2) in draws.items():
        pygame.draw.line(screen, (80,80,80), p1, p2, 40)
        seg = segments[sid]
        for car in seg.cars:
            t = car.pos / seg.length
            x = p1[0] + t * (p2[0] - p1[0])
            y = p1[1] + t * (p2[1] - p1[1])
            pygame.draw.circle(screen, (0,180,255), (int(x), int(y)), 8)

    # Avg speed
    all_cars = [c for seg in segments.values() for c in seg.cars]
    if all_cars:
        avg = sum(c.target_speed for c in all_cars) / len(all_cars)
        txt = font.render(f'Avg: {avg:.1f} m/s | Cars: {len(all_cars)}', True, (255,255,255))
        screen.blit(txt, (10, 10))

    pygame.display.flip()
