__author__ = "Ido Keysar"

import threading

import constants
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

    pygame.init()
    screen = pygame.display.set_mode((1920, 1080))
    clock = pygame.time.Clock()

    font = pygame.font.SysFont(None, 36)
    username_text = ""
    password_text = ""
    active_field = "username"
    error_message = ""
    logged_in = False

    mode = "login"

    while not logged_in:
        screen.fill((15, 15, 20))

        title_img = font.render("Login" if mode == "login" else "Register", True, (255, 255, 255))
        user_label = font.render(f"Username: {username_text}", True,
                                 (255, 255, 0) if active_field == "username" else (255, 255, 255))
        pass_label = font.render(f"Password: {'*' * len(password_text)}", True,
                                 (255, 255, 0) if active_field == "password" else (255, 255, 255))
        err_label = font.render(error_message, True, (255, 100, 100))
        #
        switch_lable = font.render("F1 to switch to REGISTER" if mode == "login" else "F1 to switch to LOGIN", True, (0, 200, 255))

        screen.blit(title_img, (100, 50))
        screen.blit(user_label, (100, 150))
        screen.blit(pass_label, (100, 200))
        screen.blit(switch_lable, (100, 250))
        screen.blit(err_label, (100, 320))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                return

            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_TAB:
                    active_field = "password" if active_field == "username" else "username"
                elif event.key == pygame.K_F1:
                    mode = "register" if mode == "login" else "login"
                    error_message = ""
                elif event.key == pygame.K_RETURN:
                    auth_msg = json.dumps(
                        {"action": mode, "username": username_text, "password": password_text}).encode()
                    send_msg(sock, session.encrypt(auth_msg))

                    raw_res = recv_msg(sock)
                    if raw_res:
                        response = json.loads(session.decrypt(raw_res).decode())
                        if response["success"]:
                            logged_in = True
                        else:
                            error_message = response["message"]

                elif event.key == pygame.K_BACKSPACE:
                    if active_field == "username":
                        username_text = username_text[:-1]
                    else:
                        password_text = password_text[:-1]

                else:
                    if active_field == "username":
                        username_text += event.unicode
                    else:
                        password_text += event.unicode

        pygame.display.flip()


    print("login")
    font = pygame.font.SysFont(None, 24)

    threading.Thread(target=receiver_thread, args=(sock, session), daemon=True).start()

    running = True

    last_move = None
    while running:
        screen.fill((30, 30, 30))
        for plat in current_game_state.get("platforms", []):
            rect_x = plat["x"] - (plat["w"] / 2)
            rect_y = plat["y"] - (plat["h"] / 2)
            pygame.draw.rect(screen, (100, 100, 100), (rect_x, rect_y, plat["w"], plat["h"]))

        for atk in current_game_state.get("attacks", []):
            rect_x = atk["x"] - (atk["w"] / 2)
            rect_y = atk["y"] - (atk["h"] / 2)
            pygame.draw.rect(screen, (255, 255, 0), (rect_x, rect_y, atk["w"], atk["h"]))

        for p in current_game_state["players"]:
            try:
                x, y = int(p["x"]), int(p["y"])
                img = font.render(f"{p['username']}  Damage: {p['hp']}%  lives: {p['lives']}", True, (255, 255, 255))
                screen.blit(img, (x - 20, y - 20))
                pygame.draw.rect(screen, (255, 0, 0), (x - (constants.defaultUserWidth/2), y - (constants.defaultUserHeight/2),
                                                       constants.defaultUserWidth, constants.defaultUserHeight ))
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


        if move_action != last_move:
            send_msg(sock, session.encrypt(json.dumps(move_action).encode()))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                action = None
                if event.key == pygame.K_SPACE:
                    action = {"action": "jump"}
                if action:
                    encrypted_action = session.encrypt(json.dumps(action).encode())
                    send_msg(sock, encrypted_action)
            if event.type == pygame.MOUSEBUTTONDOWN:
                if event.button == 1: #left click
                    atk_type = "natural"
                    if keys[pygame.K_w]:
                        atk_type = "up"
                    elif keys[pygame.K_s]:
                        atk_type = "down"
                    elif keys[pygame.K_a] or keys[pygame.K_d]:
                        atk_type = "side"

                    action = {"action": "attack", "type": atk_type}
                    encrypted_action = session.encrypt(json.dumps(action).encode())
                    send_msg(sock, encrypted_action)

        pygame.display.flip()


        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
