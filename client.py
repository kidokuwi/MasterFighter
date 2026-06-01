__author__ = "Ido Keysar"

import threading

import constants
from main import send_msg, recv_msg, SecureSession, Pose
import socket
import json
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
    sock, session = connect_to_server("127.0.0.1", constants.SERVER_PORT)

    pygame.init()
    screen = pygame.display.set_mode((constants.SCREEN_WIDTH, constants.SCREEN_HEIGHT), pygame.SCALED | pygame.FULLSCREEN | pygame.DOUBLEBUF)#you can actually just merge flags like that in pygame https://www.pygame.org/docs/ref/display.html#pygame.display.set_mode
    clock = pygame.time.Clock()

    font = pygame.font.SysFont(None, constants.FONT_SIZE_LARGE)
    username_text = ""
    password_text = ""
    active_field = "username"
    error_message = ""
    logged_in = False

    mode = "login"
    animation_page_path = "animations_falcon.png"
    animations = {}
    for anim_name in constants.FALCON_ANIMATIONS.keys(): #TAKES ALOT OF TIME :(
        animations[anim_name] = constants.get_animation(animation_page_path, constants.FALCON_ANIMATIONS, anim_name, scale=2)

    while not logged_in:
        screen.fill(constants.COLOR_BG_LOGIN)

        title_img = font.render("Login" if mode == "login" else "Register", True, constants.COLOR_WHITE)
        user_label = font.render(f"Username: {username_text}", True,
                                 constants.COLOR_ACTIVE_FIELD if active_field == "username" else constants.COLOR_WHITE)
        pass_label = font.render(f"Password: {'*' * len(password_text)}", True,
                                 constants.COLOR_ACTIVE_FIELD if active_field == "password" else constants.COLOR_WHITE)
        err_label = font.render(error_message, True, constants.COLOR_ERROR)
        #
        switch_lable = font.render("F1 to switch to REGISTER" if mode == "login" else "F1 to switch to LOGIN", True, constants.COLOR_SWITCH_LABEL)

        screen.blit(title_img, constants.LOGIN_TITLE_POS)
        screen.blit(user_label, constants.LOGIN_USERNAME_POS)
        screen.blit(pass_label, constants.LOGIN_PASSWORD_POS)
        screen.blit(switch_lable, constants.LOGIN_SWITCH_POS)
        screen.blit(err_label, constants.LOGIN_ERROR_POS)

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
    font = pygame.font.SysFont(None, constants.FONT_SIZE_SMALL)

    threading.Thread(target=receiver_thread, args=(sock, session), daemon=True).start()

    running = True
    last_move = None
    while running:

        is_started = current_game_state.get("game_started", False)
        winner = current_game_state.get("winner")

        if winner:
            screen.fill(constants.COLOR_BG_WINNER)
            win_text = font.render(f"THE WINNER IS: {winner}", True, constants.COLOR_WINNER_TEXT)
            sub_text = font.render("'R' to return to lobby", True, constants.COLOR_WHITE)

            screen.blit(win_text, (constants.SCREEN_WIDTH // 2 - constants.WINNER_TEXT_X_OFFSET, constants.WINNER_TEXT_Y))
            screen.blit(sub_text, (constants.SCREEN_WIDTH // 2 - constants.WINNER_TEXT_X_OFFSET, constants.WINNER_SUBTEXT_Y))

            for event in pygame.event.get():
                if event.type == pygame.QUIT: running = False
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_r:
                        restart_msg = {"action": "restart"}
                        send_msg(sock, session.encrypt(json.dumps(restart_msg).encode()))

        elif not is_started:
            screen.fill(constants.COLOR_BG_LOBBY)
            title = font.render("Waiting Room - 'Enter' to start", True, constants.COLOR_WHITE)
            screen.blit(title, constants.LOBBY_TITLE_POS)

            y_offset = constants.LOBBY_PLAYER_LIST_Y_START
            for p in current_game_state.get("players", []):
                player_info = f"{p['username']}  Wins: {p.get('wins', 0)}  Losses: {p.get('loses', 0)}"
                player_label = font.render(player_info, True, constants.COLOR_PLAYER_INFO)
                screen.blit(player_label, (constants.LOBBY_PLAYER_LIST_X, y_offset))
                y_offset += constants.LOBBY_PLAYER_LIST_Y_SPACING

            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False

                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE or event.key == pygame.K_q:
                        quit_action = {"action": "quit"}
                        encrypted_quit = session.encrypt(json.dumps(quit_action).encode())
                        send_msg(sock, encrypted_quit)
                        running = False
                    if event.key == pygame.K_RETURN:
                        start_msg = {"action": "start_game"}
                        send_msg(sock, session.encrypt(json.dumps(start_msg).encode()))

        else:
            screen.fill(constants.COLOR_BG_GAME)
            for plat in current_game_state.get("platforms", []):
                rect_x = plat["x"] - (plat["w"] / 2)
                rect_y = plat["y"] - (plat["h"] / 2)
                pygame.draw.rect(screen, constants.COLOR_PLATFORM, (rect_x, rect_y, plat["w"], plat["h"]))

            for item in current_game_state.get("objects", []):
                item_rect = pygame.Rect(0, 0, constants.ITEM_RENDER_WIDTH, constants.ITEM_RENDER_HEIGHT)
                item_rect.center = (int(item["x"]), int(item["y"]))
                pygame.draw.rect(screen, constants.COLOR_DROPPED_ITEM, item_rect)

            for atk in current_game_state.get("attacks", []):
                rect_x = atk["x"] - (atk["w"] / 2)
                rect_y = atk["y"] - (atk["h"] / 2)
                pygame.draw.rect(screen, constants.COLOR_ATTACK, (rect_x, rect_y, atk["w"], atk["h"]))

            dmg_lives_pos = Pose(constants.HUD_DMG_LIVES_X, constants.HUD_DMG_LIVES_Y)
            for p in current_game_state["players"]:
                try:
                    x, y = int(p["x"]), int(p["y"])
                    font = pygame.font.SysFont(None, constants.FONT_SIZE_MEDIUM)
                    img = font.render(f" {p['username']} {p['hp']}%  stocks: {p['lives']}", True, constants.COLOR_WHITE)
                    screen.blit(img, (dmg_lives_pos.x, dmg_lives_pos.y))
                    dmg_lives_pos.x += constants.HUD_PLAYER_SPACING


                    anim_frames = animations.get(p.get("state"), animations["stand"]) #if no spesific state animation then default to stand
                    frame_idx = (pygame.time.get_ticks() // constants.ANIMATION_FRAME_INTERVAL) % len(anim_frames)
                    current_frame = anim_frames[frame_idx]

                    if not p.get("facingRight"):
                        current_frame = pygame.transform.flip(current_frame, True, False)

                    img_rect = current_frame.get_rect(center=(x, y))
                    screen.blit(current_frame, img_rect)

                    if p.get("is_shielding"):
                        radius = int(p["shield_hp"]) * constants.SHIELD_VISUAL_SCALE + constants.SHIELD_VISUAL_MIN_RADIUS
                        shield_surface = pygame.Surface((radius * 2, radius * 2), pygame.SRCALPHA)
                        pygame.draw.circle(shield_surface, constants.COLOR_SHIELD, (radius, radius), radius)
                        screen.blit(shield_surface, (x - radius, y - radius))

                    font = pygame.font.SysFont(None, constants.FONT_SIZE_SMALL)
                    img = font.render(p["username"], True, constants.COLOR_WHITE)
                    screen.blit(img, (x, y + constants.USERNAME_Y_OFFSET))
                except Exception as e:
                    print(e)

            keys = pygame.key.get_pressed()
            shielding_action = False
            if keys[pygame.K_e]:#server handle if in the air
                shielding_action = True

            shield_msg = {"action": "shield", "active": shielding_action}
            send_msg(sock, session.encrypt(json.dumps(shield_msg).encode()))
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
        clock.tick(constants.CLIENT_FPS)

    pygame.quit()


if __name__ == "__main__":
    main()
