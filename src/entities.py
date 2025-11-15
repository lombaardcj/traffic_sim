import math
import pygame

# Keep constants expected by entities imported from caller context where needed

class Car:
    def __init__(self):
        self.pos = 0.0
        self.v = 0.0
        self.segment = None
        self.length = None  # set by sim when needed
        self.v0 = None
        self.a_max = None
        self.b_max = None
        self.T = None
        self.s0 = None
        self.risk = "green"
        self.colliding = False
        self.accel_state = "coasting"  # NEW: accelerating / braking / coasting        
        self.car_meta = {}  # Store calculated info: s, dv, a, s_star, etc.


class Segment:
    def __init__(self, id, start_pt, end_pt, speed_limit=13.9, car_length=4.5):
        self.id = id
        self.start = tuple(start_pt)
        self.end = tuple(end_pt)
        self.speed_limit = speed_limit
        self.cars = []
        self.outputs = []

        dx = self.end[0] - self.start[0]
        dy = self.end[1] - self.start[1]
        self.length = math.hypot(dx, dy)
        self.dir = (dx / self.length, dy / self.length) if self.length > 0 else (0, 0)
        self.car_length = car_length

    def add_car(self, car, pos=0.0):
        car.segment = self
        car.pos = pos
        # ensure car physical params exist
        if car.length is None:
            car.length = self.car_length
        self.cars.append(car)

    def remove_car(self, car):
        if car in self.cars:
            self.cars.remove(car)

    def draw_road(self, surface, world_to_screen, zoom, road_color=(80,80,80), road_width=40):
        if self.length == 0:
            return
        p1 = world_to_screen(self.start)
        p2 = world_to_screen(self.end)
        rw = max(1, int(road_width * zoom))
        pygame.draw.line(surface, road_color, p1, p2, rw)

    def draw_label(self, surface, world_to_screen, font, label_color=(200, 200, 200)):
        """Draw segment label at midpoint between start and end."""
        if self.length == 0:
            return
        mid_x = (self.start[0] + self.end[0]) / 2.0
        mid_y = (self.start[1] + self.end[1]) / 2.0
        screen_pos = world_to_screen((mid_x, mid_y))
        txt = font.render(self.id, True, label_color)
        # Center the text on the midpoint
        txt_rect = txt.get_rect(center=screen_pos)
        surface.blit(txt, txt_rect)

    def draw_cars(self, surface, world_to_screen, font, zoom, W, H, car_length_const=4.5 ,selected_car=None):
        if self.length <= 0:
            return
        s1 = world_to_screen(self.start)
        s2 = world_to_screen(self.end)
        seg_pixels = math.hypot(s2[0] - s1[0], s2[1] - s1[1])
        ppm = (seg_pixels / self.length) if self.length > 0 else 1.0

        car_pixel_length = max(4, car_length_const * ppm)
        car_pixel_width = max(2, 2.0 * ppm)
        half_len = car_pixel_length / 2.0
        half_w = car_pixel_width / 2.0

        # === STATE COLORS ===
        state_colors = {
            "accelerating": (50, 150, 255),   # Bright Blue
            "braking":      (255, 150, 50),   # Orange
            "coasting":     (180, 180, 180),  # Light Gray
        }
        risk_colors = {
            "green":  (0, 255, 0),
            "yellow": (255, 255, 0),
            "red":    (255, 0, 0),
        }

        dx = s2[0] - s1[0]
        dy = s2[1] - s1[1]
        angle = math.atan2(dy, dx)
        cos_a, sin_a = math.cos(angle), math.sin(angle)

        for car in self.cars:
            t = car.pos / self.length if self.length > 0 else 0.0
            x = self.start[0] + t * (self.end[0] - self.start[0])
            y = self.start[1] + t * (self.end[1] - self.start[1])
            sx, sy = world_to_screen((x, y))

            # === Define 4 corners: rear-left, rear-right, front-right, front-left ===
            corners_local = [
                (-half_len, -half_w),  # 0: rear-left
                (-half_len,  half_w),  # 1: rear-right
                ( half_len,  half_w),  # 2: front-right
                ( half_len, -half_w),  # 3: front-left
            ]
            rotated = []
            for px, py in corners_local:
                rx = px * cos_a - py * sin_a + sx
                ry = px * sin_a + py * cos_a + sy
                rotated.append((int(round(rx)), int(round(ry))))

            # Is this the selected car?
            if selected_car is not None and car == selected_car:
                # draw circle around car
                center_x = int(round(sx))
                center_y = int(round(sy))
                radius = int(round(max(half_len, half_w) + 6))
                pygame.draw.circle(surface, (255, 0, 255), (center_x, center_y), radius, 3)

                # Print safety distance around car (for debugging)
                # Use car_meta to get s_star if available
                if hasattr(car, 'car_meta') and 's_star' in car.car_meta:
                    # print circle with radius s_star * ppm
                    s_star = car.car_meta['s_star']
                    radius = int(round(s_star * ppm))
                    center_x = int(round(sx))
                    center_y = int(round(sy))
                    pygame.draw.circle(surface, (0, 200, 200), (center_x, center_y), radius, 1)
                
                # Do the same car_meta s
                if hasattr(car, 'car_meta') and 's' in car.car_meta:
                    # print circle with radius s * ppm
                    s_meta = car.car_meta['s']
                    radius = int(round(s_meta * ppm))
                    center_x = int(round(sx))
                    center_y = int(round(sy))
                    pygame.draw.circle(surface, (200, 200, 0), (center_x, center_y), radius, 1)

            

            # === Compute center points (midline) ===
            # rear_center  = ((rotated[0][0] + rotated[1][0]) // 2, (rotated[0][1] + rotated[1][1]) // 2)
            # rear_center  = ((rotated[0][0] + rotated[1][0]) // 2, (rotated[0][1] + rotated[1][1]) // 2)

            # Print a yellow dot at center of rear axle
            # pygame.draw.circle(surface, (255, 255, 0), rear_center, 2)

            # front_center = ((rotated[2][0] + rotated[3][0]) // 2, (rotated[2][1] + rotated[3][1]) // 2)
            # Print a red dot at center of front axle
            # pygame.draw.circle(surface, (255, 0, 0), front_center, 2)

            # === Compute center points (midline) – now in WIDTH direction ===
            # rear_center  = average of rear-left and rear-right (cross-track midline)
            # right-side midpoint (between rear-right and front-right)
            rear_center  = (
                (rotated[1][0] + rotated[2][0]) // 2,
                (rotated[1][1] + rotated[2][1]) // 2
            )

            # left-side midpoint (between rear-left and front-left)
            front_center = (
                (rotated[0][0] + rotated[3][0]) // 2,
                (rotated[0][1] + rotated[3][1]) // 2
            )
            # pygame.draw.circle(surface, (255, 255, 0), rear_center, 10)
            # pygame.draw.circle(surface, (255, 0, 0), front_center, 10)

            # # === REAR HALF (risk) — triangle: rear-left → rear-right → rear_center → close
            # rear_half = [
            #     rotated[0],           # rear-left R1
            #     rear_center,           # rear-right R2
            #     front_center,          # rear axle center R3
            #     rotated[3],           # rear-left R4
            # ]

            # # === FRONT HALF (accel state) — triangle: front_center → front-right → front-left → close
            # front_half = [
            #     rear_center,          f1
            #     rotated[1],           f2
            #     rotated[2],           f3
            #     front_center,         f4
            # ]

            # === REAR HALF (risk) — triangle: rear-left → rear-right → rear_center → close
            rear_half = [
                rotated[0],           # rear-left R1
                rotated[1],
                rear_center,          # rear axle center R3
                front_center,           # rear-left R4
            ]

            # === FRONT HALF (accel state) — triangle: front_center → front-right → front-left → close
            front_half = [
                front_center,
                rear_center,         
                rotated[2],           
                rotated[3],           
            ]


            # === DRAW ===
            if getattr(car, 'colliding', False):
                pygame.draw.polygon(surface, (180, 0, 255), rotated)
            else:
                pygame.draw.polygon(surface, risk_colors[car.risk], rear_half)
                pygame.draw.polygon(surface, state_colors[car.accel_state], front_half)

            # Border
            pygame.draw.polygon(surface, (0, 0, 0), rotated, 1)

            # # === DEBUG DOTS ===
            # for cx, cy in rotated:
                # pygame.draw.circle(surface, (255, 0, 0), (cx, cy), 5)  # yellow corners

                # # Write font index near corner
                # if font is not None:
                #     idx_txt = font.render(str(rotated.index((cx, cy))), True, (255, 255, 255))
                #     surface.blit(idx_txt, (cx + 2, cy - 10))

            # for cx, cy in rear_half:
                # pygame.draw.circle(surface, (255, 0, 0), (cx, cy), 6)    # red rear

                # Write font index near rear half point
                # if font is not None:
                #     idx_txt = font.render("R"+str(rear_half.index((cx, cy))+1), True, (255, 255, 255))
                #     surface.blit(idx_txt, (cx + 2, cy - 10))

            # for cx, cy in front_half:
                # pygame.draw.circle(surface, (0, 0, 255), (cx, cy), 4)   # blue front

            #     # Write font index near front half point
                # if font is not None:
                    # idx_txt = font.render("F"+str(front_half.index((cx, cy))+1), True, (0, 0, 255))
                    # surface.blit(idx_txt, (cx + 2, cy - 10))

            # HEADLIGHT / BEAM (scaled)
            if car.v > 2.0:
                front_x = sx + half_len * cos_a
                front_y = sy + half_len * sin_a
                beam_length_m = 6.0 + car.v * 0.6
                beam_angle = 0.4
                steps = 8
                beam_pixels = beam_length_m * ppm

                for i in range(steps):
                    alpha = int(200 * (1 - i / steps))
                    color = (255, 240, 180, alpha)
                    dist = (i + 1) / steps * beam_pixels
                    width = 2 * dist * math.tan(beam_angle)
                    p1 = (front_x, front_y)
                    p2 = (
                        front_x + dist * cos_a - width * sin_a,
                        front_y + dist * sin_a + width * cos_a
                    )
                    p3 = (
                        front_x + dist * cos_a + width * sin_a,
                        front_y + dist * sin_a - width * cos_a
                    )
                    tri_surf = pygame.Surface((W, H), pygame.SRCALPHA)
                    pygame.draw.polygon(tri_surf, color, [p1, p2, p3])
                    surface.blit(tri_surf, (0, 0))


class Junction:
    def __init__(self, id, inputs, outputs, mode="round_robin"):
        self.id = id
        self.inputs = inputs if isinstance(inputs, list) else [inputs]
        self.outputs = outputs if isinstance(outputs, list) else [outputs]
        self.mode = mode
        self.counter = 0

    def draw_junction(self, surface, world_to_screen, zoom, road_width=40, font=None):
        """Draw junction box and label above/right of the junction."""
        end_points = []
        for inp in (self.inputs if isinstance(self.inputs, list) else [self.inputs]):
            end_points.append((inp.end[0], inp.end[1]))
        if not end_points:
            return
        cx = sum(p[0] for p in end_points) // len(end_points)
        cy = sum(p[1] for p in end_points) // len(end_points)
        size = road_width * 1.3
        half = size // 2
        top_left = world_to_screen((cx - half, cy - half))
        rect_w = int(size * zoom)
        rect_h = int(size * zoom)
        rect = pygame.Rect(top_left[0], top_left[1], rect_w, rect_h)
        pygame.draw.rect(surface, (255, 255, 255), rect, max(1, int(4 * zoom)))

        center = world_to_screen((cx, cy))
        radius = int(size * 0.4 * zoom)
        if radius > 0:
            pygame.draw.circle(surface, (100, 100, 100), center, radius)
            line_len = radius * 0.8
            pygame.draw.line(surface, (200, 200, 200),
                            (center[0] - line_len, center[1] - line_len),
                            (center[0] + line_len, center[1] + line_len), max(1, int(3 * zoom)))
            pygame.draw.line(surface, (200, 200, 200),
                            (center[0] + line_len, center[1] - line_len),
                            (center[0] - line_len, center[1] + line_len), max(1, int(3 * zoom)))

        # Draw label above and to the right of junction box
        if font is not None:
            label_x = top_left[0] + rect_w + 5
            label_y = top_left[1] - 20
            txt = font.render(self.id, True, (200, 200, 200))
            surface.blit(txt, (label_x, label_y))
