__author__ = "Ido Keysar"

defaultUserWidth = 50
defaultUserHeight = 80
defaultKnockbackMult = 1
frictionMult = 0.5
gravity = 0.3

walking_speed = 5
running_speed = 10

# (dmg, rangeX, rangeY, offsetX, offsetY, attack_uptime, stun, knockbackMult, attacker_stun)
MOVE_NATURAL = (10, 50, 50, 10, 0, 1.0, 1.0, 2.0, 0.5)
MOVE_SIDE = (12, 60, 40, 15, 0, 1.2, 1.2, 2.2, 0.6)
MOVE_UP = (11, 40, 70, 5, -20, 1.1, 1.5, 2.5, 0.7)
MOVE_DOWN = (14, 60, 30, 10, 20, 1.0, 1.0, 1.5, 0.5)

MOVE_NATURAL_AIR = (9, 45, 45, 0, 0, 0.8, 0.8, 1.5, 0.4)
MOVE_SIDE_AIR = (11, 55, 35, 15, 0, 1.0, 1.1, 2.0, 0.5)
MOVE_UP_AIR = (12, 40, 60, 5, -20, 1.2, 1.2, 2.2, 0.6)
MOVE_DOWN_AIR = (15, 80, 30, -55, 40, 1.5, 1.5, 3.0, 0.8)

MOVES = {
    "natural": MOVE_NATURAL,
    "side": MOVE_SIDE,
    "up": MOVE_UP,
    "down": MOVE_DOWN,
    "natural_air": MOVE_NATURAL_AIR,
    "side_air": MOVE_SIDE_AIR,
    "up_air": MOVE_UP_AIR,
    "down_air": MOVE_DOWN_AIR
}
