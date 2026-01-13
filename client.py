# client.py
import socket
import time

from protocol import (
    UDP_PORT,
    unpack_offer,
    pack_request,
    recv_exact,
    unpack_server_payload,
    pack_client_payload,
    SERVER_PAYLOAD_SIZE,
    RESULT_NOT_OVER,
    RESULT_WIN,
    RESULT_LOSS,
    RESULT_TIE,
)

from game import card_to_string, hand_value

CLIENT_NAME = "Blackijecky-Client"

# Timeouts
TCP_CONNECT_TIMEOUT = 5.0
TCP_READ_TIMEOUT = 60.0

COOLDOWN_AFTER_SESSION = 0.0  # option to avoid reconnecting immediately on the next offer


def ask_rounds() -> int:
    while True:
        s = input("How many rounds do you want to play? (1-255): ").strip()
        try:
            n = int(s)
            if 1 <= n <= 255:
                return n
        except ValueError:
            pass
        print("Invalid input. Enter an integer between 1 and 255.")


def ask_decision() -> str:
    # Must be exactly 5 bytes: "Hittt" or "Stand"
    while True:
        d = input("Hittt or Stand? ").strip()
        if d in ("Hittt", "Stand"):
            return d
        print("Invalid input. Type exactly: Hittt or Stand")


def _result_to_text(result: int) -> str:
    if result == RESULT_WIN:
        return "WIN"
    if result == RESULT_LOSS:
        return "LOSS"
    if result == RESULT_TIE:
        return "TIE"
    return f"UNKNOWN({result})"


def _read_one_server_payload(tcp: socket.socket):
    data = recv_exact(tcp, SERVER_PAYLOAD_SIZE)
    if data is None:
        raise ConnectionError("Server closed connection.")
    parsed = unpack_server_payload(data)
    if not parsed:
        raise ValueError("Invalid server payload.")
    return parsed  # (result, rank, suit)


def play_session(tcp: socket.socket, rounds: int):
    wins = losses = ties = 0

    for r in range(1, rounds + 1):
        print(f"\n[CLIENT] === Round {r}/{rounds} ===")

        player_cards = []
        dealer_cards = []

        # Initial deal: expect 3 cards: player, player, dealer upcard (all NOT_OVER)
        for _ in range(3):
            result, rank, suit = _read_one_server_payload(tcp)
            card = (rank, suit)

            if len(player_cards) < 2:
                player_cards.append(card)
                print("[CLIENT] Player card:", card_to_string(card))
            else:
                dealer_cards.append(card)
                print("[CLIENT] Dealer upcard:", card_to_string(card))

            if result != RESULT_NOT_OVER:
                raise ValueError("Unexpected end-of-round during initial deal.")

        # Player turn
        round_done = False
        while not round_done:
            ps = hand_value(player_cards)
            print(f"[CLIENT] Player sum = {ps}")

            # If local bust happens (should occur only after receiving a Hit card),
            # do not send more decisions; just wait for server final result.
            if ps > 21:
                print("[CLIENT] Player bust locally. Waiting for server final result...")
                while True:
                    result2, r2, s2 = _read_one_server_payload(tcp)
                    if result2 != RESULT_NOT_OVER:
                        txt = _result_to_text(result2)
                        print("[CLIENT] Round result:", txt)
                        if result2 == RESULT_WIN:
                            wins += 1
                        elif result2 == RESULT_LOSS:
                            losses += 1
                        else:
                            ties += 1
                        round_done = True
                        break
                break

            decision = ask_decision()
            tcp.sendall(pack_client_payload(decision))
            print(f"[CLIENT] Sent decision: {decision}")

            if decision == "Stand":
                # Dealer phase: read until result != NOT_OVER
                revealed_hole = False
                while True:
                    result, rank, suit = _read_one_server_payload(tcp)
                    dealer_cards.append((rank, suit))
                    if not revealed_hole:
                        print("[CLIENT] Dealer reveals hole:", card_to_string((rank, suit)))
                        revealed_hole = True
                    else:
                        print("[CLIENT] Dealer draws:", card_to_string((rank, suit)))

                    if result != RESULT_NOT_OVER:
                        txt = _result_to_text(result)
                        print("[CLIENT] Round result:", txt)
                        if result == RESULT_WIN:
                            wins += 1
                        elif result == RESULT_LOSS:
                            losses += 1
                        else:
                            ties += 1
                        round_done = True
                        break
                break

            # decision == Hittt:
            # Read server response (a card; sometimes may include final result too)
            result, rank, suit = _read_one_server_payload(tcp)
            player_cards.append((rank, suit))
            print("[CLIENT] Player draws:", card_to_string((rank, suit)))

            if result != RESULT_NOT_OVER:
                txt = _result_to_text(result)
                print("[CLIENT] Round result:", txt)
                if result == RESULT_WIN:
                    wins += 1
                elif result == RESULT_LOSS:
                    losses += 1
                else:
                    ties += 1
                round_done = True
                break
            # else: loop continues; if bust locally, handled at top of loop

    total = wins + losses + ties
    win_rate = (wins / total) if total else 0.0
    print(f"\n[CLIENT] Finished playing {total} rounds, win rate: {win_rate:.2%} (W={wins}, L={losses}, T={ties})")


def main():
    # UDP listener
    udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    if hasattr(socket, "SO_REUSEPORT"):
        try:
            udp.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        except OSError:
            pass

    udp.bind(("", UDP_PORT))
    print(f"[CLIENT] Client started, listening for offers on UDP port {UDP_PORT}...")

    while True:
        data, (ip, _) = udp.recvfrom(2048)
        parsed = unpack_offer(data)
        if not parsed:
            continue

        tcp_port, server_name = parsed
        if tcp_port == 0:
            continue

        print(f"\n[CLIENT] Received offer from {ip} name={server_name} tcp_port={tcp_port}")
        rounds = ask_rounds()

        tcp = None
        try:
            tcp = socket.create_connection((ip, tcp_port), timeout=TCP_CONNECT_TIMEOUT)
            tcp.settimeout(TCP_READ_TIMEOUT)

            req = pack_request(rounds, CLIENT_NAME)
            tcp.sendall(req)
            print("[CLIENT] Request sent successfully! Starting session...")

            play_session(tcp, rounds)

        except (OSError, ValueError, ConnectionError) as e:
            print(f"[CLIENT] Session failed: {e}")

        finally:
            try:
                if tcp:
                    tcp.close()
            except Exception:
                pass

        print(f"[CLIENT] Returning to listening (cooldown {COOLDOWN_AFTER_SESSION}s)...\n")
        time.sleep(COOLDOWN_AFTER_SESSION)


if __name__ == "__main__":
    main()
