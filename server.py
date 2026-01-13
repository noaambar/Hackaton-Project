# server.py
import socket
import threading
from typing import Tuple

from protocol import (
    UDP_PORT,
    pack_offer,
    recv_exact,
    unpack_request,
    unpack_client_payload,
    pack_server_payload,
    REQUEST_SIZE,
    CLIENT_PAYLOAD_SIZE,
    RESULT_NOT_OVER,
    RESULT_WIN,
    RESULT_LOSS,
    RESULT_TIE,
)

from game import create_deck, hand_value, card_to_string

SERVER_NAME = "Blackijecky"
TCP_BACKLOG = 50

# Timeouts (seconds)
TCP_CLIENT_TIMEOUT = 120.0  # waiting for client decisions / messages

def get_local_ip() -> str:
    """
    Best-effort way to get the LAN IP used to reach the outside.
    Doesn't actually send packets.
    """
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    except OSError:
        return "0.0.0.0"
    finally:
        s.close()


def udp_broadcast_loop(tcp_port: int, stop_event: threading.Event):
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)

    msg = pack_offer(tcp_port, SERVER_NAME)
    print(f"[SERVER] Broadcasting offers on UDP {UDP_PORT} (tcp_port={tcp_port})")

    while not stop_event.is_set():
        try:
            udp.sendto(msg, ("<broadcast>", UDP_PORT))
        except OSError:
            # Broadcast may fail on some networks; keep trying.
            pass
        stop_event.wait(1.0)

    udp.close()


def send_card(conn: socket.socket, card: Tuple[int, int], result_code: int = RESULT_NOT_OVER):
    rank, suit = card
    conn.sendall(pack_server_payload(result_code, rank, suit))


def play_one_round(conn: socket.socket) -> int:
    """
    Plays one simplified blackjack round.
    Returns result code: RESULT_WIN / RESULT_LOSS / RESULT_TIE
    Protocol convention:
      - Server sends cards in the exact order events happen.
      - Final message has result != 0 and repeats the last card sent.
    """
    deck = create_deck()
    player = [deck.pop(), deck.pop()]
    dealer = [deck.pop(), deck.pop()]

    print(f"    [ROUND] Player: {card_to_string(player[0])}, {card_to_string(player[1])}")
    print(f"    [ROUND] Dealer upcard: {card_to_string(dealer[0])} (hole hidden)")

    # Initial deal: player 2 cards, dealer 1 upcard (all NOT_OVER)
    send_card(conn, player[0], RESULT_NOT_OVER)
    send_card(conn, player[1], RESULT_NOT_OVER)
    send_card(conn, dealer[0], RESULT_NOT_OVER)
    last_card_sent = dealer[0]

    # Player turn: hit/stand repeatedly until bust or stand
    while True:
        if hand_value(player) > 21:
            print(f"    [ROUND] Player busts with {hand_value(player)}")
            # bust: send final result with last drawn card (the bust-causing card is already in player[-1])
            last_card_sent = player[-1]
            send_card(conn, last_card_sent, RESULT_LOSS)
            return RESULT_LOSS

        data = recv_exact(conn, CLIENT_PAYLOAD_SIZE)
        if data is None:
            raise ConnectionError("Client disconnected during player turn.")
        decision = unpack_client_payload(data)
        if decision is None:
            raise ConnectionError("Invalid client payload")

        print(f"    [ROUND] Client decision: {decision}")

        if decision == "Hittt":
            card = deck.pop()
            player.append(card)
            last_card_sent = card
            print(f"    [ROUND] Player draws: {card_to_string(card)} (sum={hand_value(player)})")
            send_card(conn, card, RESULT_NOT_OVER)
            continue

        # Stand
        break

    # Dealer turn (only if player didn't bust)
    print(f"    [ROUND] Dealer reveals hole: {card_to_string(dealer[1])}")
    last_card_sent = dealer[1]
    send_card(conn, dealer[1], RESULT_NOT_OVER)

    while hand_value(dealer) < 17:
        card = deck.pop()
        dealer.append(card)
        last_card_sent = card
        print(f"    [ROUND] Dealer draws: {card_to_string(card)} (sum={hand_value(dealer)})")
        send_card(conn, card, RESULT_NOT_OVER)

        if hand_value(dealer) > 21:
            print(f"    [ROUND] Dealer busts with {hand_value(dealer)}")
            send_card(conn, last_card_sent, RESULT_WIN)
            return RESULT_WIN

    # Decide winner
    ps = hand_value(player)
    ds = hand_value(dealer)

    if ps > 21:
        result = RESULT_LOSS
    elif ds > 21:
        result = RESULT_WIN
    elif ps > ds:
        result = RESULT_WIN
    elif ps < ds:
        result = RESULT_LOSS
    else:
        result = RESULT_TIE

    print(f"    [ROUND] Final totals: player={ps}, dealer={ds} -> result={result}")
    send_card(conn, last_card_sent, result)
    return result


def handle_client(conn: socket.socket, addr):
    conn.settimeout(TCP_CLIENT_TIMEOUT)
    try:
        req = recv_exact(conn, REQUEST_SIZE)
        if req is None:
            return
        parsed = unpack_request(req)
        if not parsed:
            print(f"[SERVER] Invalid request from {addr}. Closing.")
            return

        rounds, client_name = parsed
        if rounds < 1:
            rounds = 1

        print(f"[SERVER] Client '{client_name}' connected from {addr} for {rounds} rounds")

        for i in range(1, rounds + 1):
            print(f"[SERVER] --- Round {i}/{rounds} for '{client_name}' ---")
            play_one_round(conn)

        print(f"[SERVER] Finished session for '{client_name}' ({addr})")

    except socket.timeout:
        print(f"[SERVER] Timeout waiting for client {addr}. Closing.")
    except (ConnectionError, OSError) as e:
        print(f"[SERVER] Connection error with {addr}: {e}")
    finally:
        try:
            conn.close()
        except OSError:
            pass


def main():
    tcp = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    tcp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    tcp.bind(("", 0))  # pick an available port
    tcp.listen(TCP_BACKLOG)

    tcp_port = tcp.getsockname()[1]
    print(f"Server started, listening on IP address {ip} (TCP port {tcp_port})")

    stop_event = threading.Event()
    t = threading.Thread(target=udp_broadcast_loop, args=(tcp_port, stop_event), daemon=True)
    t.start()

    try:
        while True:
            conn, addr = tcp.accept()
            threading.Thread(target=handle_client, args=(conn, addr), daemon=True).start()
    except KeyboardInterrupt:
        print("\n[SERVER] Shutting down...")
    finally:
        stop_event.set()
        try:
            tcp.close()
        except OSError:
            pass


if __name__ == "__main__":
    main()
