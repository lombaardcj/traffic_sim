import pygame, random, sys, math
import config as cfg
pygame.init()

# config/state management moved into `sim` module (use sim.update_config_current_state / sim.reset_to_default_state)

# Load config on startup (module handles file path)
config = cfg.config
if config is None:
    print("Failed to load config. Please ensure config.json exists.")
    sys.exit(1)

# === SCREEN ===
W, H = 700, 700
screen = pygame.display.set_mode((W, H))
clock = pygame.time.Clock()
font = pygame.font.SysFont(None, 20)
label_font_size = 16
label_font = pygame.font.SysFont(None, label_font_size)

# Give window a better title
pygame.display.set_caption('Traffic Simulation — traffic_sim')

# Fullscreen toggle state (Ctrl+F will toggle fullscreen)
is_fullscreen = False
stored_window_size = (W, H)

# === VIEW / ZOOM / PAN ===
ZOOM = 1.0           # global zoom (1.0 = 100%)
MIN_ZOOM = 0.1
MAX_ZOOM = 7.5
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

def toggle_fullscreen():
    """Toggle fullscreen and compensate pan for screen size change."""
    global W, H, is_fullscreen, screen, PAN_X, PAN_Y, stored_window_size
    old_w, old_h = W, H
    is_fullscreen = not is_fullscreen
    if is_fullscreen:
        stored_window_size = (W, H)
        screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN)
        info = pygame.display.Info()
        W, H = info.current_w, info.current_h
    else:
        W, H = stored_window_size
        screen = pygame.display.set_mode((W, H), pygame.RESIZABLE)
    
    # Compensate for size change: center the view by adjusting pan
    # When screen grows, we need to shift pan to keep center on same world point
    width_delta = (W - old_w) / 2.0
    height_delta = (H - old_h) / 2.0
    PAN_X += width_delta
    PAN_Y += height_delta



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

# === ENTITIES / SIM separations ===
import entities
import sim

# Initialize sim state from config
sim.build_from_config(config)


# Simulation state is managed in `sim` module
segments = sim.segments
junctions = sim.junctions
spawn_rate = sim.spawn_rate
spawn_timer = sim.spawn_timer

# Use simulation implementations from sim module
update_cars = sim.update_cars
transfer_at_junction = sim.transfer_at_junction
# spawn_rate / spawn_timer are provided by sim module

# === MAIN LOOP ===
accumulator = 0
sim_tick = 0
sim_time = 0.0
show_help = config['current_state']['view'].get('show_help', False)
show_labels = config['current_state']['view'].get('show_labels', True)
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
            # === FULLSCREEN TOGGLE (Ctrl+F) ===
            if e.key == pygame.K_f and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                toggle_fullscreen()
                continue
            # === HELP TOGGLE (H key) ===
            if e.key == pygame.K_h:
                show_help = not show_help
                continue
            # === LABELS TOGGLE (L key) ===
            if e.key == pygame.K_l:
                show_labels = not show_labels
                continue
            # === PLUS/MINUS ZOOM ===
            if e.key == pygame.K_PLUS or e.key == pygame.K_EQUALS or e.key == pygame.K_KP_PLUS:
                zoom_at(pygame.mouse.get_pos(), 1.1)
            elif e.key == pygame.K_MINUS or e.key == pygame.K_KP_MINUS:
                zoom_at(pygame.mouse.get_pos(), 0.9)
            
            # === SPAWN CAR ===
            if e.key == pygame.K_SPACE:
                north = sim.segments.get('northsouth')
                if north is not None and (not north.cars or north.cars[-1].pos > 30):
                    sim.spawn_into('northsouth')

            # === SAVE CONFIG (Ctrl+S) ===
            if e.key == pygame.K_s and (pygame.key.get_mods() & pygame.KMOD_CTRL):
                sim.update_config_current_state(config)
                # also save view
                config.setdefault('current_state', {})
                config['current_state'].setdefault('view', {})
                config['current_state']['view']['zoom'] = ZOOM
                config['current_state']['view']['pan_x'] = PAN_X
                config['current_state']['view']['pan_y'] = PAN_Y
                config['current_state']['view']['show_help'] = show_help
                config['current_state']['view']['show_labels'] = show_labels
                cfg.save_config(config)
                print("Config saved to config.json")

            # === RESET TO DEFAULT (R key) ===
            if e.key == pygame.K_r:
                sim.reset_to_default_state(config)
                # reset view too
                default = config.get('default_state', {})
                if 'view' in default:
                    ZOOM = default['view'].get('zoom', ZOOM)
                    PAN_X = default['view'].get('pan_x', PAN_X)
                    PAN_Y = default['view'].get('pan_y', PAN_Y)
                print("Reset to default state")

    if spawn_timer > 1.0 / max(1e-6, sim.spawn_rate):
        north = sim.segments.get('northsouth')
        if north is not None and (not north.cars or north.cars[-1].pos > 30):
            sim.spawn_into('northsouth')
        spawn_timer = 0

    while accumulator >= STEP:
        for seg in sim.segments.values():
            sim.update_cars(seg, STEP)

        # === TRANSFER VIA JUNCTIONS ===
        for j in sim.junctions:
            sim.transfer_at_junction(j)

        # Advance simulation time / ticks
        sim_tick += 1
        sim_time += STEP

        accumulator -= STEP

    # === RENDER ===
    screen.fill((30, 30, 30))

    # Draw all roads
    for seg in sim.segments.values():
        seg.draw_road(screen, world_to_screen, ZOOM, road_width=ROAD_WIDTH)

    # Draw all junctions
    for junc in sim.junctions:
        junc.draw_junction(screen, world_to_screen, ZOOM, road_width=ROAD_WIDTH, font=font)

    # Draw all cars
    for seg in sim.segments.values():
        seg.draw_cars(screen, world_to_screen, ZOOM, W, H, car_length_const=CAR_LENGTH)

    # Draw segment labels at their midpoints
    if show_labels:
        for seg in sim.segments.values():
            seg.draw_label(screen, world_to_screen, label_font)

    # Help screen
    if show_help:
        help_lines = [
            "=== KEYBOARD SHORTCUTS ===",
            "H: Toggle help",
            "L: Toggle labels",
            "SPACE: Spawn car",
            "Ctrl+F: Toggle fullscreen",
            "Ctrl+S: Save config",
            "R: Reset to default",
            "+/-: Zoom in/out",
            "Mouse Wheel: Zoom",
            "Right-Click + Drag: Pan",
        ]
        y_offset = 10
        for line in help_lines:
            help_txt = font.render(line, True, (200, 200, 100))
            screen.blit(help_txt, (10, y_offset))
            y_offset += 20
        y_offset += 10
    else:
        y_offset = 10

    # Stats - always show tick/time regardless of car count
    all_cars = [c for seg in sim.segments.values() for c in seg.cars]
    sim_time_txt = font.render(f'Time: {sim_time:.2f}s', True, (255,255,255))
    tick_txt = font.render(f'Ticks: {sim_tick}', True, (255,255,255))

    screen.blit(sim_time_txt, (10, y_offset))
    screen.blit(tick_txt, (10, y_offset + 15))
    
    if all_cars:
        avg_v = sum(c.v for c in all_cars) / len(all_cars)
        red = sum(1 for c in all_cars if c.risk == "red")
        stats_txt = font.render(f'Avg: {avg_v:.1f} m/s | Cars: {len(all_cars)} | Red: {red}', True, (255,255,255))
        screen.blit(stats_txt, (10, y_offset + 30))

    pygame.display.flip()
