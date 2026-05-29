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
    def __init__(self, dmg, rangeX, rangeY, offsetX, offsetY, attack_uptime, stun, knockbackMult, attacker_stun):
        self.dmg = dmg
        self.rangeX = rangeX
        self.rangeY = rangeY
        self.offsetX = offsetX
        self.offsetY = offsetY
        self.attack_uptime = attack_uptime
        self.stun = stun
        self.knockbackMult = knockbackMult
        self.attacker_stun = attacker_stun

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
        return (distanceX <= (self.width/2 + other.width/2)) and (distanceY <= (self.height/2 + other.height/2))
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

        self.jumps_remain = 0

        self.facingRight = False
        self.stunTimer = 0
        self.invinciblityTimer = 0
        self.attkCooldown = 0

        self.current_movement = "none"
        self.is_running = False

        self.jump_cooldown = 0

        self.isDead = False
        self.lives = 3#TODO:CONSTANTS

    def isFacingRight(self):
        return 1 if self.facingRight else 0

    def isStunned(self):
        return self.stunTimer > 0
    def isInvincible(self):
        return self.invinciblityTimer > 0
    def isOnAttackCooldown(self):
        return self.attkCooldown > 0

    def get_state_string(self):
        if not self.isOnGround:
            if self.jumps_remain == 1: return "jump"
            if self.jumps_remain == 0: return "doubleJump"

        if self.current_movement != "none":
            return "run" if self.is_running else "walk"

        return "stand"


    def updateStatuses(self, timePassed):
        self.stunTimer = max(0, self.stunTimer - timePassed)
        self.invinciblityTimer = max(0, self.invinciblityTimer - timePassed)
        self.attkCooldown = max(0, self.attkCooldown - timePassed)
        self.jump_cooldown = max(0, self.jump_cooldown - timePassed)

    def updatePose(self, timePassed):
        if self.current_movement != "none" and not self.isStunned():
            move_speed = constants.running_speed if self.is_running else constants.walking_speed
            if self.current_movement == "left":
                self.velX = -move_speed
                self.facingRight = False
            elif self.current_movement == "right":
                self.velX = move_speed
                self.facingRight = True

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
        self.active_attks = []#lst of {hitbox, time}
        self.winner = None

    def update(self, timePassed):
        if self.winner:
            return

        for player in self.players.keys():
            player.updatePose(timePassed)
            player.updateStatuses(timePassed)
            player.isOnGround = False
            if self.sessionMap:
                for platform in self.sessionMap.platforms:
                    if player.hitBox.checkCollision(platform.hitBox) and player.velY >= 0:
                        player.isOnGround = True
                        player.jumps_remain = 2
                        player.currentPose.y = platform.hitBox.pose.y - platform.hitBox.height/2 - player.hitBox.height/2 # - = +
                        player.velY = 0
            if player.currentPose.y > 1100 or player.currentPose.x < -200 or player.currentPose.x > 2100 or player.currentPose.y < -300:
                if not player.isDead:
                    player.lives -= 1
                    player.hp = 0
                    if player.lives <= 0:
                        player.isDead = True
                        player.currentPose.x = -9999# send player out of scene
                        player.currentPose.y = -9999
                        player.velX = 0
                        player.velY = 0
                    else:
                        player.currentPose.x = 400#TODO:CONSTANTS
                        player.currentPose.y = 300
                        player.velX = 0
                        player.velY = 0
                        player.current_movement = "none"
                        player.is_running = False
                        player.stunTimer = 0
                        player.invinciblityTimer = 2.0 #TODO:CONSTANTS

                if len(self.players) > 1:
                    players_alive = [p for p in self.players.keys() if not p.isDead]
                    if len(players_alive) == 1:
                        self.winner = players_alive[0].user
                    elif len(players_alive) == 0:
                        self.winner = "tie"
        active_attacks = self.active_attks
        for attack in active_attacks:
            attack['timer'] -= timePassed
            attacker = attack["attacker"]
            direction = 1 if attacker.facingRight else -1
            attack["x"] = attacker.currentPose.x + ((attacker.hitBox.width / 2) + (attacker.hitBox.width / 2) + (attack['w'] / 2) + attack['offsetX'])*direction
            attack['y'] = attacker.currentPose.y + attack['offsetY']

            atk_pose = Pose(attack['x'], attack['y'])
            atk_hitbox = HitBox(atk_pose, attack['w'], attack['h'])

            for player in self.players.keys():
                if player != attack['attacker'] and not player.isInvincible():
                    if atk_hitbox.checkCollision(player.hitBox):
                        player.hp += attack['dmg']
                        direction = 1 if attack['attacker'].facingRight else -1
                        player.velX += (player.hp**2) * constants.defaultKnockbackMult * direction
                        player.velY -= constants.defaultKnockbackMult
                        player.stunTimer = attack['stun']

                        player.invinciblityTimer = 0.2#TODO:CONSTANTS
                        print(f"hit {player.user.username} during uptime")

            if attack['timer'] <= 0:
                self.active_attks.remove(attack)


    def handleAttack(self, attacker, attackType):
        if attacker.isStunned() or attacker.isOnAttackCooldown(): return

        real_type = attackType
        if not attacker.isOnGround:
            real_type = f"{attackType}_air"

        move = attacker.weapon.moves.get(real_type)
        if not move:
            return

        direction = 1 if attacker.facingRight else -1
        attackX = attacker.currentPose.x + ((attacker.hitBox.width / 2) +
                    (attacker.hitBox.width / 2) + (move.rangeX / 2) + move.offsetX) * direction
        attackY = attacker.currentPose.y + (move.offsetY)

        attacker.attkCooldown = move.attack_uptime + 0.1
        attacker.stunTimer = move.attacker_stun

        self.active_attks.append({
            "attacker": attacker,
            "x": attackX,
            "y": attackY,
            "w": move.rangeX,
            "h": move.rangeY,
            "offsetX": move.offsetX,
            "offsetY": move.offsetY,
            "timer": move.attack_uptime,
            "dmg": move.dmg,
            "stun": move.stun
        })


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
        self.session = GameSession([], self.clients, SessionMap([Platform(Pose(400,500), 800, 100),
                                                                 Platform(Pose(200,300), 150, 50),
                                                                 Platform(Pose(600,300), 150, 50),

                                                                 Platform(Pose(1500, 500), 800, 100),
                                                                 Platform(Pose(1300, 300), 150, 50),
                                                                 Platform(Pose(1700, 300), 150, 50)
                                                                 ], "unnammed"))
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
        num_of_failed = 0
        try:
            session = self.handshake(client_socket)
            logged_in = False
            while(not logged_in):
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
                logged_in = success
                if not success:
                    num_of_failed += 1
                    print(f"Login/reg failed from: {client_socket}")
                if(num_of_failed > 10): # too much, TODO:CONSTANTS
                    client_socket.close()
                    return

            moves = {}
            for move_name, move_stats in constants.MOVES.items():
                moves[move_name] = Attack(*move_stats)# * is cool way to put tuple into args

            no_weapon = Weapon("none", moves)
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
        winner = None
        if self.session.winner:
            if isinstance(self.session.winner, str):
                winner = self.session.winner  # tie
            else:
                winner = self.session.winner.username  # user

        game_state = {"players" : [],
                      "platforms": [],
                      "attacks": [],
                      "winner": winner}
        players = self.clients.keys()
        for player in players:
            game_state["players"].append({"username" : player.user.username, "x":player.currentPose.x, "y":player.currentPose.y,
                                          "hp": player.hp, "facingRight" : player.facingRight
                                        , "weapon" : player.weapon.name if player.weapon else "None", "isInvincible": player.isInvincible(),
                                          "isStunned": player.isStunned(), "isOnAttackCooldown": player.isOnAttackCooldown(),
                                          "lives": player.lives,"isDead": player.isDead, "state": player.get_state_string()})
        if self.session.sessionMap:
            for plat in self.session.sessionMap.platforms:
                game_state["platforms"].append({"x": plat.hitBox.pose.x,"y": plat.hitBox.pose.y,"w": plat.hitBox.width,"h": plat.hitBox.height})
        for atk in self.session.active_attks:
            game_state["attacks"].append({
                "x": atk["x"], "y": atk["y"],
                "w": atk["w"], "h": atk["h"]
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
        db_updated = False
        while True:
            start_time = time.time()
            while not self.input_queue.empty():
                player, msg = self.input_queue.get()
                if msg.get("action") == "restart" and self.session.winner:
                    self.session.winner = None
                    db_updated = False
                    for p in self.clients.keys():
                        p.lives = 3#TODO:CONSTANTS
                        p.isDead = False
                        p.hp = 0
                        p.currentPose = Pose(400, 400)#TODO:CONSTANTS
                        p.velX = 0
                        p.velY = 0
                    continue
                self.process_input(player, msg)

            self.session.update(1 / 60) #60fps might change later TODO: put in constants
            if self.session.winner and not db_updated:
                if self.session.winner != "tie":
                    winner = self.session.winner
                    self.user_manager.users[winner.username]["wins"] += 1
                    for p in self.clients.keys():
                        if (p != winner):
                            self.user_manager.users[p.user.username]["loses"] += 1
                    self.user_manager.save_db()
                db_updated = True
            self.broadcast_state()


            sleep_time = 1/60 - (time.time() - start_time)
            if (sleep_time > 0):
                time.sleep(sleep_time)

    def process_input(self, player, msg):

        if player.isStunned():
            return

        action = msg.get("action")
        if action == "attack":
            self.session.handleAttack(player, msg.get("type"))

        elif action == "move":
            player.current_movement = msg.get("direction")
            player.is_running = msg.get("run")
            if player.current_movement == "none":
                player.velX = 0


        elif action == "jump":
            if player.jump_cooldown > 0:
                return

            if player.isOnGround:
                player.velY = -9
                player.isOnGround = False
                player.can_double_jump = True
                player.has_doubleJamped = False
                player.jump_cooldown = 0.1
                player.jumps_remain = 1
                print("jump")

            elif player.jumps_remain > 0:
                player.velY = -9
                player.has_doubleJamped = True
                player.can_double_jump = False
                player.jump_cooldown = 0.1
                player.jumps_remain -= 1
                print("doublejump")






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
