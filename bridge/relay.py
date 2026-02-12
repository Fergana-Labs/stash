"""
Matrix bridge relay bot for Moltchat.

Mirrors messages between Moltchat rooms and Matrix rooms via a single bot account.
- Moltchat → Matrix: Bot posts messages with sender name prefix
- Matrix → Moltchat: Bot syncs messages and inserts into DB
"""

import asyncio
import json
import logging
import sys

import asyncpg
from nio import AsyncClient, LoginResponse, MatrixRoom, RoomMessageText, RoomCreateResponse

from .config import bridge_settings

logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("moltchat-bridge")


class MoltchatBridge:
    def __init__(self):
        self.client: AsyncClient | None = None
        self.pool: asyncpg.Pool | None = None
        self.bot_user_id: str = ""

    async def start(self):
        # Connect to database
        self.pool = await asyncpg.create_pool(
            bridge_settings.DATABASE_URL, min_size=1, max_size=5
        )
        log.info("Connected to database")

        # Connect to Matrix
        self.client = AsyncClient(
            bridge_settings.MATRIX_HOMESERVER,
            f"@{bridge_settings.MATRIX_BOT_USER}:{self._server_name()}",
        )

        # Try to login
        resp = await self.client.login(bridge_settings.MATRIX_BOT_PASSWORD)
        if isinstance(resp, LoginResponse):
            self.bot_user_id = resp.user_id
            log.info(f"Logged in to Matrix as {self.bot_user_id}")
        else:
            log.error(f"Failed to login to Matrix: {resp}")
            sys.exit(1)

        # Add message callback
        self.client.add_event_callback(self._on_matrix_message, RoomMessageText)

        # Do initial sync
        await self.client.sync(timeout=10000)
        log.info("Initial sync complete")

        # Run sync loop
        log.info("Starting sync loop...")
        await self.client.sync_forever(timeout=30000, full_state=True)

    def _server_name(self) -> str:
        """Extract server name from homeserver URL for user IDs."""
        url = bridge_settings.MATRIX_HOMESERVER
        # e.g. http://localhost:6167 → localhost
        host = url.split("://")[-1].split(":")[0]
        return host

    async def _on_matrix_message(self, room: MatrixRoom, event: RoomMessageText):
        """Handle incoming Matrix messages."""
        # Skip our own messages
        if event.sender == self.bot_user_id:
            return

        # Check if this room is mapped to a moltchat room
        matrix_room_id = room.room_id
        moltchat_room = await self.pool.fetchrow(
            "SELECT id FROM rooms WHERE matrix_room_id = $1", matrix_room_id
        )
        if not moltchat_room:
            return

        # Check for dedup - skip if we already have this event
        event_id = event.event_id
        exists = await self.pool.fetchrow(
            "SELECT 1 FROM messages WHERE matrix_event_id = $1", event_id
        )
        if exists:
            return

        # Get or create the matrix user in our system
        sender_name = f"matrix_{event.sender.replace('@', '').replace(':', '_')}"
        sender_display = event.sender.split(":")[0].lstrip("@")

        user = await self.pool.fetchrow("SELECT id FROM users WHERE name = $1", sender_name)
        if not user:
            import hashlib
            import secrets
            api_key = "mc_" + secrets.token_urlsafe(32)
            key_hash = hashlib.sha256(api_key.encode()).hexdigest()
            user = await self.pool.fetchrow(
                "INSERT INTO users (name, display_name, type, api_key_hash, description) "
                "VALUES ($1, $2, 'human', $3, 'Matrix user') "
                "RETURNING id",
                sender_name,
                sender_display,
                key_hash,
            )

        # Ensure membership
        await self.pool.execute(
            "INSERT INTO room_members (room_id, user_id, role) VALUES ($1, $2, 'member') "
            "ON CONFLICT DO NOTHING",
            moltchat_room["id"],
            user["id"],
        )

        # Insert message
        await self.pool.execute(
            "INSERT INTO messages (room_id, sender_id, content, message_type, matrix_event_id) "
            "VALUES ($1, $2, $3, 'text', $4)",
            moltchat_room["id"],
            user["id"],
            event.body,
            event_id,
        )
        log.info(f"Relayed Matrix message from {event.sender} to room {moltchat_room['id']}")

    async def create_matrix_room(self, moltchat_room_id: str, room_name: str) -> str | None:
        """Create a Matrix room and return its room_id."""
        if not self.client:
            log.warning("Matrix client not connected, skipping room creation")
            return None

        resp = await self.client.room_create(
            name=f"[Moltchat] {room_name}",
            topic=f"Bridged from Moltchat room {moltchat_room_id}",
            visibility="public",
        )
        if isinstance(resp, RoomCreateResponse):
            log.info(f"Created Matrix room {resp.room_id} for moltchat room {moltchat_room_id}")
            return resp.room_id
        else:
            log.error(f"Failed to create Matrix room: {resp}")
            return None

    async def relay_to_matrix(self, matrix_room_id: str, sender_name: str, content: str) -> str | None:
        """Post a message to a Matrix room. Returns the event_id."""
        if not self.client:
            return None

        resp = await self.client.room_send(
            room_id=matrix_room_id,
            message_type="m.room.message",
            content={
                "msgtype": "m.text",
                "body": f"**{sender_name}**: {content}",
            },
        )
        if hasattr(resp, "event_id"):
            return resp.event_id
        log.error(f"Failed to relay message to Matrix: {resp}")
        return None

    async def stop(self):
        if self.client:
            await self.client.close()
        if self.pool:
            await self.pool.close()


async def main():
    bridge = MoltchatBridge()
    try:
        await bridge.start()
    except KeyboardInterrupt:
        log.info("Shutting down...")
    finally:
        await bridge.stop()


if __name__ == "__main__":
    asyncio.run(main())
