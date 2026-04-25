__author__ = "Ido Keysar"
import constants

class Pose:
    def __init__(self, x, y):
        self.x = x
        self.y = y
class Attack:
    def __init__(self, dmg, rangeX, rangeY, offsetX, offsetY, atkSpeed, stun, knockbackMult):
        self.dmg = dmg
        self.rangeX = rangeX
        self.rangeY = rangeY
        self.offsetX = offsetX
        self.offsetY = offsetY
        self.atkSpeed = atkSpeed
        self.stun = stun
        self.knockbackMult = knockbackMult

class Weapon:
    def __init__(self, name):
        self.name = name
        self.moves = {} # prob implement left right up down + spacial

    def addMove(self, moveType, attackObj):
        self.moves[moveType] = attackObj
class HitBox:
    def __init__(self, pose, width, height):
        self.pose = pose
        self.width = width
        self.height = height
    def checkCollision(self, other):
        distanceX = abs(other.pose.x - self.pose.x)
        distanceY = abs(other.pose.y - self.pose.y)
        return (distanceX < (self.width/2 + other.width/2)) and (distanceY < (self.height/2 + other.height/2))
class User:
    def __init__(self, username, password, wins, loses):
        self.username = username
        self.password = password
        self.wins = wins
        self.loses = loses

class Player:
    def __init__(self, user, currentPose, weapon):
        self.user = user
        self.currentPose = currentPose
        self.weapon = weapon
        self.hp = 0
        self.hitBox = HitBox(self.currentPose, constants.defaultUserWidth , constants.defaultUserHeight)
        self.velX = 0
        self.velY = 0
        self.isOnGround = False

        self.facingRight = False
        self.stunTimer = 0
        self.invinciblityTimer = 0
        self.attkCooldown = 0

    def isFacingRight(self):
        return 1 if self.facingRight else 0

    def isStunned(self):
        return self.stunTimer > 0
    def isInvincible(self):
        return self.invinciblityTimer > 0
    def isOnAttackCooldown(self):
        return self.attkCooldown > 0
    def updateStatuses(self, timePassed):
        if self.isStunned():
            self.stunTimer -= timePassed
        if self.isInvincible():
            self.invinciblityTimer -= timePassed
        if self.isOnAttackCooldown():
            self.attkCooldown -= timePassed

    def updatePose(self, timePassed):
        self.updateStatuses(timePassed)
        if not self.isOnGround:
            self.velY += constants.gravity
        self.currentPose.x += self.velX
        self.currentPose.y += self.velY

        self.velX *= constants.frictionMult

class GameSession:
    def __init__(self, objects, players, sessionMap):
        self.objects = objects
        self.players = players # player:sock
        self.sessionMap = sessionMap

    def update(self, timePassed):
        for player in self.players.keys():
            player.updatePose(timePassed)

    def handleAttack(self, attacker, attackType):
        if attacker.isStunned() or attacker.isOnAttackCooldown(): return

        move = attacker.weapon.moves.get(attackType)
        direction = 1
        if (attacker.velX < 0): direction = -1
        attackX = attacker.currentPose.x + (move.offsetX*direction)
        attackY = attacker.currentPose.y + (move.offsetY)
        attackPose = Pose(attackX, attackY)
        attackHitbox = HitBox(attackPose, move.rangeX, move.rangeY)

        attacker.attkCooldown = move.atkSpeed

        for player in self.players:
            if player != attacker:
                if attackHitbox.checkCollision(player):
                    player.hp += move.dmg
                    print(f"hit {player.user.username}")
                    player.velX += player.hp*constants.defaultKnockbackMult*direction
                    if attackType == "up":
                        player.velY += player.hp*constants.defaultKnockbackMult*direction
                    elif attackType == "down":
                        player.velY -= player.hp*constants.defaultKnockbackMult*direction
