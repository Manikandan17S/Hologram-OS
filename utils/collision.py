def point_vs_rect(point, rect):
    """
    Checks if a point (x, y) is inside a rect (x, y, w, h).
    """
    px, py = point
    rx, ry, rw, rh = rect
    
    return rx <= px <= rx + rw and ry <= py <= ry + rh

def rect_vs_rect(r1, r2):
    """
    Checks if two rects intersect.
    r1, r2: (x, y, w, h)
    """
    return (r1[0] < r2[0] + r2[2] and
            r1[0] + r1[2] > r2[0] and
            r1[1] < r2[1] + r2[3] and
            r1[1] + r1[3] > r2[1])

def point_vs_circle(point, circle_center, radius):
    """
    Checks if point is inside a circle.
    """
    px, py = point
    cx, cy = circle_center
    return (px - cx)**2 + (py - cy)**2 <= radius**2
