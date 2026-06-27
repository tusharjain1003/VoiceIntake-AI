"""
Smoke test for the WebSocket intake endpoint.

Connects a WebSocket client and runs a simple happy-path scenario.
"""

from fastapi.testclient import TestClient

from backend.main import app


def test_ws_handshake() -> None:
    """Verify the WebSocket endpoint responds to start/text messages."""
    client = TestClient(app)

    with client.websocket_connect("/ws/intake/new") as ws:
        # Should receive session_id immediately upon connecting
        sid_msg = ws.receive_json()
        assert sid_msg["type"] == "session_id", f"Expected session_id, got {sid_msg['type']}"
        session_id = sid_msg["id"]
        assert session_id != "new"
        print(f"  ✓ session_id received: {session_id}")

        # Send start
        ws.send_json({"type": "start"})
        greeting = ws.receive_json()
        assert greeting["type"] == "agent_text", f"Expected agent_text, got {greeting['type']}"
        assert greeting["text"] != ""
        print("  ✓ greeting received")

        # Read the two extra messages that follow start
        state = ws.receive_json()
        assert state["type"] == "state_update"
        fields = ws.receive_json()
        assert fields["type"] == "fields_update"
        print("  ✓ start sequence complete")

        # Send a text message
        ws.send_json({"type": "text", "message": "John Smith"})

        # Expect agent_text
        msg1 = ws.receive_json()
        assert msg1["type"] == "agent_text"
        print(f"  ✓ agent_text: {msg1['text'][:60]}...")

        # Expect fields_update
        msg2 = ws.receive_json()
        assert msg2["type"] == "fields_update"
        assert msg2["fields"]["patient_name"]["value"] == "John Smith"
        print(f"  ✓ fields_update: name={msg2['fields']['patient_name']['value']}")

        # Expect state_update
        msg3 = ws.receive_json()
        assert msg3["type"] == "state_update"
        assert msg3["current_node"] is not None
        print(f"  ✓ state_update: node={msg3['current_node']}")

        # Send stop
        ws.send_json({"type": "stop"})


def test_ws_unknown_type() -> None:
    """Verify unknown message types produce an error."""
    client = TestClient(app)

    with client.websocket_connect("/ws/intake/new") as ws:
        ws.receive_json()  # session_id
        ws.send_json({"type": "foobar"})
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "Unknown message type" in err["message"]
        print(f"  ✓ unknown type error: {err['message']}")


def test_ws_binary_audio() -> None:
    """Verify binary audio frames are accepted without breaking the protocol."""
    client = TestClient(app)

    with client.websocket_connect("/ws/intake/new") as ws:
        ws.receive_json()  # session_id

        # Send a few binary chunks simulating WebM/Opus
        for _ in range(3):
            ws.send_bytes(b"\x00" * 1024)  # 1 KB chunk

        # Normal text flow must still work
        ws.send_json({"type": "text", "message": "John Smith"})
        msg = ws.receive_json()
        assert msg["type"] == "agent_text"
        msg = ws.receive_json()
        assert msg["type"] == "fields_update" or msg["type"] == "state_update"
        print("  ✓ binary audio frames accepted, text flow intact")


def test_ws_bad_session() -> None:
    """Verify connecting to a non-existent session returns an error."""
    client = TestClient(app)

    with client.websocket_connect("/ws/intake/nonexistent-session-id") as ws:
        err = ws.receive_json()
        assert err["type"] == "error"
        assert "not found" in err["message"].lower()
        print(f"  ✓ bad session error: {err['message']}")


if __name__ == "__main__":
    print("WebSocket smoke tests:\n")
    test_ws_handshake()
    test_ws_unknown_type()
    test_ws_binary_audio()
    test_ws_bad_session()
    print("\nAll WebSocket smoke tests passed.")
