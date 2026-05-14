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
        except:
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
    screen = pygame.display.set_mode((800, 600))
    clock = pygame.time.Clock()

    running = True
    while running:
        for p in current_game_state["players"]:
            pygame.draw.rect(screen, (255, 0, 0), (int(p["x"]), int(p["y"]), 50, 50))
            font = pygame.font.SysFont(None, 24)
            img = font.render(p["username"], True, (255, 255, 255))
            screen.blit(img, (p["x"], p["y"] - 20))

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                running = False

            if event.type == pygame.KEYDOWN:
                action = None
                if event.key == pygame.K_SPACE:
                    action = {"action": "attack", "type": "neutral"}

                if action:
                    encrypted_action = session.encrypt(json.dumps(action).encode())
                    send_msg(sock, encrypted_action)

        screen.fill((30, 30, 30))
        pygame.display.flip()
        clock.tick(60)

    pygame.quit()


if __name__ == "__main__":
    main()
