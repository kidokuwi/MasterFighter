import constants

class Pose:
    def __init__(self, x, y):
        self.x = x
        self.y = y
class Weapon:
    def __init__(self, name, dmg, rangeX, rangeY, offsetX, offsetY, atkSpeed, stun):
        self.name = name
        self.dmg = dmg
        self.rangeX = rangeX
        self.rangeY = rangeY
        self.offsetX = offsetX
        self.offsetY = offsetY
        self.atkSpeed = atkSpeed
        self.stun = stun
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

        self.stunTimer = 0
        self.invinciblityTimer = 0
        self.attkCooldown = 0


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
        self.currentPose.pose.x += self.velX
        self.currentPose.pose.y += self.velY

        self.velX *= constants.frictionMult

class GameSession:
    def __init__(self, objects, players, map):
        self.objects = objects
        self.players = players # player:sock
        self.map = map
    def update(self):
        pass
    def handleAttack(self, attacker):
        if attacker.isStunned() or attacker.isOnAttackCooldown(): return

        direction = 1
        if (attacker.velX < 0): direction = -1
        attackX = attacker.currentPose.x + (attacker.weapon.offsetX*direction)
        attackY = attacker.currentPose.x + (attacker.weapon.offsetY)
        attackPose = Pose(attackX, attackY)
        attackHitbox = HitBox(attackPose, attacker.weapon.rangeX, attacker.weapon.rangeY)

        attacker.attkCooldown = attacker.weapon.atkSpeed

        for player in self.players:
            if player != attacker:
                if attackHitbox.checkCollision(player):
                    player.hp += attacker.weapon.dmg
                    print(f"hit {player.name}")
                    player.velX += player.hp*constants.defaultKnockbackMult*direction
