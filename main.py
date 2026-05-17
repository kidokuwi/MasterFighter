__author__ = "Ido Keysar"

import hashlib
import secrets
import time
from threading import main_thread

import constants
import socket
import threading
import json
import queue
from cryptography.hazmat.primitives.asymmetric import rsa, padding
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.backends import default_backend
import os

PEPPER = "2222222" #TODO:PUT
PRIVATE_KEY_FILE = "private_key.pem"
PUBLIC_KEY_FILE = "public_key.pem"
KEY_PASSWORD = b'11111111' # to secure rsa

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
    def __init__(self, name, moves):
        self.name = name
        self.moves = moves # prob implement left right up down + spacial

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

        self.has_doubleJamped = False

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
        self.stunTimer = max(0, self.stunTimer - timePassed)
        self.invinciblityTimer = max(0, self.invinciblityTimer - timePassed)
        self.attkCooldown = max(0, self.attkCooldown - timePassed)

    def updatePose(self, timePassed):
        self.updateStatuses(timePassed)
        if not self.isOnGround:
            self.velY += constants.gravity
        else:
            self.velX *= constants.frictionMult
        self.velX *= constants.frictionMult
        self.currentPose.x += self.velX
        self.currentPose.y += self.velY


class Platform:
    def __init__(self, pose, width, height):
        self.hitBox = HitBox(pose, width, height)


class UserManager:
    def __init__(self, db_file="users.json"):
        self.db_file = db_file
        self.users = self.load_db()

    def load_db(self):
        if os.path.exists(self.db_file):
            with open(self.db_file, "r") as f: return json.load(f)
        return {}

    def save_db(self):
        with open(self.db_file, "w") as f: json.dump(self.users, f)

    def register(self, username, password):
        if username in self.users: return False

        salt = secrets.token_hex(16)
        hashed_pw = hashlib.sha256((password + salt + PEPPER).encode()).hexdigest()

        self.users[username] = {
            "password": hashed_pw,
            "salt": salt,
            "wins": 0,
            "loses": 0
        }
        self.save_db()
        return True

    def login(self, username, password):
        user_data = self.users.get(username)
        if not user_data: return False

        check_hash = hashlib.sha256((password + user_data["salt"] + PEPPER).encode()).hexdigest()
        return check_hash == user_data["password"]


class SessionMap:
    def __init__(self, platforms, name):
        self.platforms = platforms
        self.name = name

class GameSession:
    def __init__(self, objects, players, sessionMap):
        self.objects = objects
        self.players = players # player:sock
        self.sessionMap = sessionMap

    def update(self, timePassed):
        for player in self.players.keys():
            player.updatePose(timePassed)
            player.isOnGround = False
            if self.sessionMap:
                for platform in self.sessionMap.platforms:
                    if player.hitBox.checkCollision(platform.hitBox):
                        player.isOnGround = True
                        player.has_doubleJamped = False
                        player.currentPose.y = platform.hitBox.pose.y - platform.hitBox.height/2 - player.hitBox.height/2 # - = +
                        player.velY = 0


    def handleAttack(self, attacker, attackType):
        if attacker.isStunned() or attacker.isOnAttackCooldown(): return

        move = attacker.weapon.moves.get(attackType)
        direction = 1 if (attacker.facingRight) else -1
        attackX = attacker.currentPose.x + (move.offsetX*direction)
        attackY = attacker.currentPose.y + (move.offsetY)
        attackPose = Pose(attackX, attackY)
        attackHitbox = HitBox(attackPose, move.rangeX, move.rangeY)

        attacker.attkCooldown = move.atkSpeed

        for player in self.players:
            if player != attacker and not player.isInvincible():
                if attackHitbox.checkCollision(player.hitBox):

                    player.hp += move.dmg
                    print(f"hit {player.user.username}")
                    player.velX += player.hp*constants.defaultKnockbackMult*direction
                    player.stunTimer = move.stun
                    if attackType == "up":
                        player.velY += player.hp*constants.defaultKnockbackMult*direction
                    elif attackType == "down":
                        player.velY -= player.hp*constants.defaultKnockbackMult*direction


def send_msg(sock, data):
    length = str(len(data)).zfill(8) #TODO: CONSTANTS
    sock.sendall(length.encode() + data)


def recv_msg(sock):
    header = sock.recv(8)
    if not header: return None
    length = int(header.decode())

    chunks = []
    bytes_recd = 0
    while bytes_recd < length:
        chunk = sock.recv(min(length - bytes_recd, 2048))
        if not chunk: break
        chunks.append(chunk)
        bytes_recd += len(chunk)
    return b"".join(chunks)

class SecureSession:
    def __init__(self, key):
        self.aesgcm = AESGCM(key)

    def encrypt(self, plaintext_bytes):
        nonce = os.urandom(12)
        ciphertext = self.aesgcm.encrypt(nonce, plaintext_bytes, b"")
        return nonce + ciphertext

    def decrypt(self, data):
        nonce = data[:12]
        ciphertext = data[12:]
        return self.aesgcm.decrypt(nonce, ciphertext, b"")


class GameServer:
    def __init__(self, host, port):
        self.server_socket = socket.socket()
        self.server_socket.bind((host, port))
        self.server_socket.listen()

        self.input_queue = queue.Queue()
        self.clients = {} #Player:socket
        self.session = GameSession([], self.clients, SessionMap([Platform(Pose(400,500), 800, 100)], "unnammed"))
        self.user_manager = UserManager("users.json")

        self.private_key, self.public_key_bytes = self.get_keys()
        self.client_sessions = {}  #socket:SecureSession

    def get_keys(self):
        if os.path.exists(PRIVATE_KEY_FILE):
            with open(PRIVATE_KEY_FILE, "rb") as f:
                private_key = serialization.load_pem_private_key(f.read(), password=KEY_PASSWORD, backend=default_backend())

            public_key_bytes = private_key.public_key().public_bytes(encoding=serialization.Encoding.PEM,format=serialization.PublicFormat.SubjectPublicKeyInfo)

        else:
            private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
            pem_private = private_key.private_bytes(encoding=serialization.Encoding.PEM,format=serialization.PrivateFormat.PKCS8,
                encryption_algorithm=serialization.BestAvailableEncryption(KEY_PASSWORD))
            public_key_bytes = private_key.public_key().public_bytes(encoding=serialization.Encoding.PEM,format=serialization.PublicFormat.SubjectPublicKeyInfo)

            with open(PRIVATE_KEY_FILE, "wb") as f:
                f.write(pem_private)

        return private_key, public_key_bytes

    def handshake(self, client_socket):
        send_msg(client_socket, self.public_key_bytes)

        encrypted_aes_key = recv_msg(client_socket)

        aes_key = self.private_key.decrypt(
            encrypted_aes_key,
            padding.OAEP(
                mgf=padding.MGF1(algorithm=hashes.SHA256()),
                algorithm=hashes.SHA256(),
                label=None
            )
        )
        return SecureSession(aes_key)

    def handle_client(self, client_socket):
        player = None
        try:
            session = self.handshake(client_socket)

            auth_data = recv_msg(client_socket)
            if not auth_data: return

            auth_json = json.loads(session.decrypt(auth_data).decode())
            action = auth_json.get("action")  # should be login/register
            username = auth_json.get("username")
            password = auth_json.get("password")

            if action == "register":
                success = self.user_manager.register(username, password)
                msg = "Register successful" if success else "Invalid registeration"
            else:  # login
                success = self.user_manager.login(username, password)
                msg = "Login successful" if success else "Invalid username or password"

            response = json.dumps({"success": success, "message": msg}).encode()
            send_msg(client_socket, session.encrypt(response))

            if not success:
                client_socket.close()
                return

            no_weapon = Weapon("none", {"right" : Attack(10,50,50,10,0,
                                                         10,1,2),
                                        "left" : Attack(10,50,50,10,0,
                                                         10,1,2),
                                        "natural" : Attack(10,50,50,10,0,
                                                         10,1,2)})
            db_user = self.user_manager.users[username]
            user_obj = User(username, db_user["password"], db_user["wins"], db_user["loses"])
            player = Player(user_obj, Pose(300, 400), no_weapon)

            self.clients[player] = client_socket
            self.client_sessions[client_socket] = session

            while True:
                encrypted_data = recv_msg(client_socket)
                if not encrypted_data: break

                decrypted_json = session.decrypt(encrypted_data).decode()
                message = json.loads(decrypted_json)
                self.input_queue.put((player, message))

        except Exception as e:
            print(f"Error handling client: {e}")
        finally:
            if player in self.clients:
                del self.clients[player]
            if client_socket in self.client_sessions:
                del self.client_sessions[client_socket]
            client_socket.close()

    def broadcast_state(self):
        game_state = {"players" : [],
                      "platforms": []}
        players = self.clients.keys()
        for player in players:
            game_state["players"].append({"username" : player.user.username, "x":player.currentPose.x, "y":player.currentPose.y,
                                          "hp": player.hp, "facingRight" : player.facingRight
                                        , "weapon" : player.weapon.name if player.weapon else "None", "isInvincible": player.isInvincible(),
                                          "isStunned": player.isStunned(), "isOnAttackCooldown": player.isOnAttackCooldown()})
        if self.session.sessionMap:
            for plat in self.session.sessionMap.platforms:
                game_state["platforms"].append({
                    "x": plat.hitBox.pose.x,
                    "y": plat.hitBox.pose.y,
                    "w": plat.hitBox.width,
                    "h": plat.hitBox.height
                })

        json_state = json.dumps(game_state).encode()
        for player in players:
            try:
                session = self.client_sessions[self.clients[player]]
                if session:
                    send_msg(self.clients[player], session.encrypt(json_state))
            except Exception as e:
                print(f"Error handling client:{player.user.username} : {e}")


    def main_loop(self):
        while True:
            start_time = time.time()
            while not self.input_queue.empty():
                player, msg = self.input_queue.get()
                self.process_input(player, msg)

            self.session.update(1 / 60) #60fps might change later TODO: put in constants
            self.broadcast_state()


            sleep_time = 1/60 - (time.time() - start_time)
            if (sleep_time > 0):
                time.sleep(sleep_time)

    def process_input(self, player, msg):
        action = msg.get("action")
        if action == "attack":
            self.session.handleAttack(player, msg.get("type"))

        elif action == "move":
            direction = msg.get("direction")
            move_speed = constants.walking_speed if not msg.get("run") else constants.running_speed
            if direction == "left":
                player.velX = -move_speed
                player.facingRight = False
            elif direction == "right":
                player.velX = move_speed
                player.facingRight = True
            elif direction == "none":
                player.velX = 0
        elif action == "jump":
            if (not player.isOnGround and not player.has_doubleJamped):
                player.velY -= 2 #TODO:CONSTANTS
                player.has_doubleJamped = True
                print("doublejamped")
            elif (player.isOnGround):
                player.velY -= 3
                print("jumped")






if __name__ == "__main__":
    server = GameServer("0.0.0.0", 3141)
    main_game_thread = threading.Thread(target=server.main_loop, daemon=True)
    main_game_thread.start()
    print("started!!!!!")
    try:
        while True:
            cli_sock, addr = server.server_socket.accept()
            print("conection from", addr)
            cli_thread = threading.Thread(target=server.handle_client, args=(cli_sock, ))
            cli_thread.start()
    except Exception as e:
        print(e)
    finally:
        server.server_socket.close()
