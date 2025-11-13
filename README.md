# traffic_sim
Experimental traffic simulator

## Install venv
```
python -m venv .venv
source .venv/bin/activate
```

## Install pip requirements
```
pip install -r requirements
```

## Run the sim
```
python ./src/main.py
```

## Teak the variables
# === IDM PARAMETERS (Intelligent Driver Model) ===
# All values based on real-world traffic studies (NGSIM, HighD, Treiber et al.)
# Units: meters (m), seconds (s), meters per second (m/s), m/s²

A_MAX = 2.0
# Maximum comfortable acceleration
# Unit: m/s²
# Meaning: How quickly a driver can speed up when unobstructed
# Typical: 1.0–3.0 m/s² (human drivers), 3.0–5.0 for aggressive or AVs
# Effect: ↑ = faster starts, smoother flow | ↓ = sluggish response

B_MAX = 3.0
# Maximum comfortable deceleration (braking)
# Unit: m/s²
# Meaning: How hard a driver brakes in normal conditions (not emergency)
# Typical: 2.0–4.0 m/s² (humans), up to 8.0 in panic
# Effect: ↑ = stronger reaction to gaps → more shockwaves | ↓ = gentler, less jam-prone

V0 = 13.9
# Desired free-flow speed (cruise speed when no leader)
# Unit: m/s
# 13.9 m/s = 50 km/h ≈ 31 mph
# Typical: 13.9–33.3 m/s (50–120 km/h) depending on road type
# Effect: ↑ = higher capacity | Must match speed_limit or be capped

T = 1.5
# Safe time headway
# Unit: seconds
# Meaning: Minimum time gap to the car in front at current speed
# Example: at 10 m/s, wants 15 m gap
# Typical: 1.0–1.8 s (1.5 is standard for highways)
# Effect: ↑ = lower density, fewer jams | ↓ = denser flow, more red cars

S0 = 2.0
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