import math, random
from entities import Segment, Car, Junction

# Simulation-level constants will be set by caller or assumed defaults
STEP = 0.05
CAR_LENGTH = 4.5
MARGIN = 4.0

# Simulation state
segments = {}
junctions = []
spawn_rate = 0.8
spawn_timer = 0

# Helper functions moved from main

def idm_acceleration(car, s, dv, v_free):
    if s <= 0:
        return -car.b_max
    v_ratio = car.v / v_free if v_free > 0 else 0
    s_star = car.s0 + max(0, car.v * car.T + (car.v * dv) / (2 * math.sqrt(car.a_max * car.b_max)))
    interaction = (s_star / s) ** 2 if s > 0 else 10.0
    a = car.a_max * (1 - v_ratio**4 - interaction)
    return max(-car.b_max, min(car.a_max, a))


def get_leader(seg, car_idx):
    car = seg.cars[car_idx]

    # local leader
    if car_idx > 0:
        leader = seg.cars[car_idx - 1]
        s = leader.pos - car.pos - leader.length
        dv = car.v - leader.v
        return s, dv

    best_s = float('inf')
    best_dv = 0
    visited = set()
    queue = [(seg, seg.length)]

    while queue:
        current_seg, dist_offset = queue.pop(0)
        if current_seg.id in visited:
            continue
        visited.add(current_seg.id)

        if current_seg.cars:
            rear_car = min(current_seg.cars, key=lambda c: c.pos)
            s = dist_offset + rear_car.pos - car.pos - rear_car.length
            dv = car.v - rear_car.v
            if s < best_s:
                best_s = s
                best_dv = dv

        outputs = []
        if hasattr(current_seg, 'outputs') and current_seg.outputs:
            outputs = current_seg.outputs
        for out_seg in outputs:
            if out_seg.id not in visited:
                queue.append((out_seg, dist_offset + out_seg.length))

    return (best_s, best_dv) if best_s != float('inf') else (float('inf'), 0)


def update_cars(seg, STEP_local=0.05):
    if not seg.cars:
        return
    seg.cars.sort(key=lambda c: c.pos, reverse=True)
    for i, car in enumerate(seg.cars):
        v_free = min(car.v0, seg.speed_limit)
        s, dv = get_leader(seg, i)
        a = idm_acceleration(car, s, dv, v_free)
        car.v = max(0, car.v + a * STEP_local)
        car.pos += car.v * STEP_local

        car.colliding = False
        if i > 0:
            leader = seg.cars[i-1]
            actual_gap = leader.pos - car.pos - leader.length
            if actual_gap < 0:
                car.colliding = True
                leader.colliding = True

        if s == float('inf'):
            car.risk = "green"
            risk_reason = "No leader ahead"
        else:
            s_star = car.s0 + max(0, car.v * car.T + (car.v * dv) / (2 * math.sqrt(car.a_max * car.b_max)))
            if s <= s_star:
                car.risk = "red"
                risk_reason = f"Gap {round(s, 2)}m <= Desired {round(s_star, 2)}m (too close)"
            elif s <= s_star + MARGIN:
                car.risk = "yellow"
                risk_reason = f"Gap {round(s, 2)}m in warning zone ({round(s_star, 2)}m to {round(s_star + MARGIN, 2)}m)"
            else:
                car.risk = "green"
                risk_reason = f"Gap {round(s, 2)}m > Safe threshold"
        
        # Store metadata for display
        car.car_meta = {
            's': s if s != float('inf') else 'inf',
            'dv': round(dv, 2),
            'a': round(a, 2),
            's_star': round(s_star if s != float('inf') else 0, 2),
            'v_free': round(v_free, 2),
            'segment_id': seg.id,
            'risk_reason': risk_reason,
        }


def transfer_at_junction(junction):
    for input_seg in junction.inputs:
        exiting = [c for c in input_seg.cars if c.pos >= input_seg.length]
        for car in exiting:
            input_seg.remove_car(car)
            if junction.mode == "round_robin":
                output = junction.outputs[junction.counter % len(junction.outputs)]
                junction.counter += 1
            elif junction.mode in ["priority", "fixed"]:
                output = junction.outputs[0]
            else:
                output = random.choice(junction.outputs)

            entry = 0
            if output.cars:
                first_car = min(output.cars, key=lambda c: c.pos)
                min_gap = car.length + first_car.length + car.s0
                if first_car.pos < min_gap:
                    input_seg.add_car(car, input_seg.length - 0.1)
                    continue
            output.add_car(car, entry)
            car.v = min(car.v, output.speed_limit)


def build_from_config(config):
    """Initialize segments and junctions from config['current_state'] or default."""
    global segments, junctions, spawn_rate, spawn_timer
    segments = {}
    junctions = []

    state = config.get('current_state', config.get('default_state', {}))
    pts = state.get('points', {})

    # create segments
    for seg_data in state.get('segments', []):
        seg = Segment(seg_data['id'], seg_data['start'], seg_data['end'], seg_data.get('speed_limit', 13.9), car_length=CAR_LENGTH)
        segments[seg.id] = seg

    # wire outputs (by id references in config we expect 'outputs' to be ids)
    # The config uses names for inputs/outputs in junctions; handle both string ids and lists
    for jdata in state.get('junctions', []):
        inputs = []
        for inp in jdata.get('inputs', []):
            if isinstance(inp, str) and inp in segments:
                inputs.append(segments[inp])
            elif hasattr(inp, 'id'):
                inputs.append(inp)
            else:
                # if config had single id stored as string
                if inp in segments:
                    inputs.append(segments[inp])
        outputs = []
        for out in jdata.get('outputs', []):
            if isinstance(out, str) and out in segments:
                outputs.append(segments[out])
            elif hasattr(out, 'id'):
                outputs.append(out)
        j = Junction(jdata['id'], inputs if len(inputs)>1 else (inputs[0] if inputs else []), outputs if len(outputs)>1 else (outputs[0] if outputs else []), mode=jdata.get('mode','priority'))
        junctions.append(j)

    # After creating junctions, ensure segments have outputs lists if needed (some junction definitions expect this)
    # Walk junctions and add outputs where appropriate
    for j in junctions:
        for inp in j.inputs:
            if inp and isinstance(inp, Segment):
                inp.outputs = j.outputs if isinstance(j.outputs, list) else [j.outputs]

    spawn_rate = state.get('spawn_rate', spawn_rate)
    spawn_timer = 0


def update_config_current_state(config):
    """Write current segments/junctions state back into config['current_state'].
    Only stores geometric/structural info (start/end/speed_limit and junction modes) and leaves cars out.
    """
    state = config.setdefault('current_state', {})
    state.setdefault('segments', [])
    state.setdefault('junctions', [])

    # segments
    seg_list = []
    for seg in segments.values():
        seg_list.append({
            'id': seg.id,
            'start': [seg.start[0], seg.start[1]],
            'end': [seg.end[0], seg.end[1]],
            'speed_limit': seg.speed_limit
        })
    state['segments'] = seg_list

    # junctions
    j_list = []
    for j in junctions:
        j_list.append({
            'id': j.id,
            'inputs': [s.id for s in j.inputs],
            'outputs': [s.id for s in (j.outputs if isinstance(j.outputs, list) else [j.outputs])],
            'mode': j.mode
        })
    state['junctions'] = j_list

    # view will be handled by caller (main)


def reset_to_default_state(config):
    build_from_config(config)


def spawn_into(segment_id):
    if segment_id not in segments:
        return None
    car = Car()
    # set car parameters defaults (caller can override)
    car.length = CAR_LENGTH
    car.v0 = 33.3
    car.a_max = 3.0
    car.b_max = 4.0
    car.T = 1.8
    car.s0 = 3.0
    segments[segment_id].add_car(car, 0)
    return car
