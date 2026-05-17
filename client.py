__author__ = "Ido Keysar"

import threading

from main import send_msg, recv_msg, SecureSession
import socket
import json
import os
import pygame
from cryptography.hazmat.primitives import serialization, hashes
from cryptography.hazmat.primitives.asymmetric import padding
from cryptography.hazmat.primitives.ciphers.aead import AESGCM


current_game_state = {"players": []}


def receiver_thread(sock, session):
    global current_game_state
    while True:
        try:
            data = recv_msg(sock)
            if not data: break

            decrypted = session.decrypt(data)
            current_game_state = json.loads(decrypted.decode())
        except Exception as e:
            print(e)
            break


def connect_to_server(host, port):
    client_socket = socket.socket()
    client_socket.connect((host, port))

    public_key_bytes = recv_msg(client_socket)
    public_key = serialization.load_pem_public_key(public_key_bytes)

    aes_key = AESGCM.generate_key(bit_length=256)
    session = SecureSession(aes_key)

    encrypted_aes_key = public_key.encrypt(aes_key, padding.OAEP(mgf=padding.MGF1(algorithm=hashes.SHA256()), algorithm=hashes.SHA256(), label=None))

    send_msg(client_socket, encrypted_aes_key)

    return client_socket, session


def main():
    sock, session = connect_to_server("127.0.0.1", 3141)

    username = input("Username: ")
    password = input("Password: ")
    auth_msg = json.dumps({
        "action": "login",
        "username": username,
        "password": password
    }).encode()

    send_msg(sock, session.encrypt(auth_msg))

    response = json.loads(session.decrypt(recv_msg(sock)).decode())

    if not response["success"]:
        print(f"{response['message']}")
        return

    print("login")
    threading.Thread(target=receiver_thread, args=(sock, session), daemon=True).start()


    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    clock = pygame.time.Clock()

    running = True
    while running:
        screen.fill((30, 30, 30))
        for plat in current_game_state.get("platforms", []):
            rect_x = plat["x"] - (plat["w"] / 2)
            rect_y = plat["y"] - (plat["h"] / 2)
            pygame.draw.rect(screen, (100, 100, 100), (rect_x, rect_y, plat["w"], plat["h"]))


        for p in current_game_state["players"]:
            try:
                x, y = int(p["x"]), int(p["y"])
                pygame.draw.rect(screen, (255, 0, 0), (x, y, 50, 50))
                font = pygame.font.SysFont(None, 24)
                img = font.render(p["username"], True, (255, 255, 255))
                screen.blit(img, (x, y - 20))
            except Exception as e:
                print(e)

        keys = pygame.key.get_pressed()
        move_action = None

        player_running = False
        if (keys[pygame.K_LSHIFT] or keys[pygame.K_RSHIFT]):
            player_running = True

        if keys[pygame.K_a]:
            move_action = {"action": "move", "direction": "left", "run": player_running}
        elif keys[pygame.K_d]:
            move_action = {"action": "move", "direction": "right" , "run": player_running}
        else:
            move_action = {"action": "move", "direction": "none" , "run": player_running}

        send_msg(sock, session.encrypt(json.dumps(move_action).encode()))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                action = None
                if event.key == pygame.K_SPACE:
                    action = {"action": "jump"}
                if event.key == pygame.MOUSEBUTTONDOWN:
                    action = {"action": "attack", "type" : "natural"}

                if action:
                    encrypted_action = session.encrypt(json.dumps(action).encode())
                    send_msg(sock, encrypted_action)

        pygame.display.flip()


        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
