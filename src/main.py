import pygame, random, sys
pygame.init()

W, H = 1000, 300
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 28)

PIXELS_PER_METER = 2
STEP = 0.05

class Road:
    def __init__(self):
        self.segments = [{'length': 400, 'speed_limit': 13.9}]
    def speed_limit_at(self, pos):
        return self.segments[0]['speed_limit']

road = Road()
cars = []

def spawn():
    if not cars or cars[-1].pos > 20:
        cars.append(type('Car', (), {'pos':0.0, 'length':4.5, 'min_gap':2.0}))

accumulator = 0
spawn_timer = 0
spawn_rate = 1.0   # cars per second

while True:
    dt = clock.tick(60)/1000.0
    accumulator += dt
    spawn_timer += dt
    if spawn_timer > 1/spawn_rate:
        spawn(); spawn_timer = 0

    for e in pygame.event.get():
        if e.type == pygame.QUIT: sys.exit()
        if e.type == pygame.KEYDOWN and e.key == pygame.K_SPACE: spawn()

    while accumulator >= STEP:
        # ---- UPDATE ----
        for i in range(len(cars)-1, -1, -1):
            car = cars[i]
            leader_pos = cars[i+1].pos if i+1 < len(cars) else float('inf')
            gap = leader_pos - car.pos - (cars[i+1].length if i+1 < len(cars) else 0)
            safe = float('inf') if gap > car.min_gap else 0
            car.target_speed = min(road.speed_limit_at(car.pos), safe)
            car.pos += car.target_speed * STEP
            if car.pos > road.segments[0]['length'] + 50:
                cars.pop(i)
        accumulator -= STEP

    # ---- RENDER ----
    screen.fill((30,30,30))
    # road
    pygame.draw.rect(screen, (90,90,90), (0, H//2-20, W, 40))
    # cars
    for c in cars:
        x = int(c.pos * PIXELS_PER_METER)
        pygame.draw.rect(screen, (0,180,255), (x, H//2-15, int(c.length*PIXELS_PER_METER), 30))
    # avg speed
    if cars:
        avg = sum(c.target_speed for c in cars)/len(cars)
        txt = font.render(f'Avg speed: {avg:.1f} m/s', True, (255,255,255))
        screen.blit(txt, (10,10))

    pygame.display.flip()
    