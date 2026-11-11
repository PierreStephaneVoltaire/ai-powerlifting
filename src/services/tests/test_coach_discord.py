import asyncio
import json
from contextlib import asynccontextmanager

from fastapi.testclient import TestClient

from services.coach_discord.app import create_app
from services.coach_discord.gateway import NOT_LINKED, Relay, chunks, conversation_for
from services.coach_discord.store import Registration, RegistrationStore

ACCESS = {'X-PL-Access-Context': json.dumps({'workload': 'cluster.local/ns/powerlifting/sa/powerlifting-app-backend'})}


class Directory:
    def __init__(self, people):
        self.people = people

    def resolve(self, discord_id):
        from services.coach_discord.users import Identity
        person = self.people.get(str(discord_id))
        return Identity(person, person) if person else None


class FakeTable:
    def __init__(self, items=None):
        self.items = {(item["pk"], item["sk"]): item for item in items or []}

    def put_item(self, Item):
        self.items[(Item["pk"], Item["sk"])] = dict(Item)

    def get_item(self, Key):
        item = self.items.get((Key["pk"], Key["sk"]))
        return {"Item": item} if item else {}

    def query(self, KeyConditionExpression, FilterExpression=None, **_):
        partition = KeyConditionExpression.get_expression()["values"][1]
        items = [item for (pk, _), item in self.items.items() if pk == partition]
        if FilterExpression is not None:
            wanted = FilterExpression.get_expression()["values"][1]
            items = [item for item in items if item.get("status") == wanted]
        return {"Items": items}

    def update_item(self, Key, UpdateExpression, ExpressionAttributeNames, ExpressionAttributeValues):
        self.items[(Key["pk"], Key["sk"])]["status"] = ExpressionAttributeValues[":inactive"]


class FakeGateway:
    def __init__(self):
        self.attached = []
        self.detached = []
        self.channels = {}

    def attach(self, registration):
        self.attached.append(registration.webhook_id)
        self.channels[registration.webhook_id] = {registration.channel_id}

    def detach(self, registration):
        self.detached.append(registration.webhook_id)
        self.channels.pop(registration.webhook_id, None)

    def listening(self, registration):
        return registration.webhook_id in self.channels

    async def close(self):
        pass


class FakeCoach:
    def __init__(self, reply="ok"):
        self.reply = reply
        self.asked = []
        self.resets = []

    async def ask(self, person, athlete, conversation_id, text, discord_subject):
        self.asked.append((person, athlete, conversation_id, text))
        return self.reply

    async def reset(self, person, athlete, conversation_id, discord_subject):
        self.resets.append((person, conversation_id))


class FakeChannel:
    def __init__(self, channel_id=42):
        self.id = channel_id
        self.sent = []

    @asynccontextmanager
    async def typing(self):
        yield

    async def send(self, text):
        self.sent.append(text)


class FakeAuthor:
    def __init__(self, author_id):
        self.id = author_id
        self.bot = False


class FakeMessage:
    def __init__(self, author_id, channel):
        self.author = FakeAuthor(author_id)
        self.channel = channel
        self.replies = []

    async def reply(self, text, mention_author=True):
        self.replies.append(text)


def store_with(items=None):
    return RegistrationStore("if-webhooks", "powerlifting", "ca-central-1", table=FakeTable(items))


def test_store_writes_if_webhooks_items_under_its_own_partition():
    store = store_with()
    registration = store.create(Registration(label="workout", bot_token="bot", channel_id="42"))
    item = store.table.items[("powerlifting", registration.webhook_id)]
    assert item["platform"] == "discord" and item["status"] == "active"
    assert json.loads(item["config_json"]) == {"bot_token": "bot", "channel_id": "42"}
    assert store.get(registration.webhook_id).bot_token == "bot"


def test_store_ignores_other_partitions_activity_rows_and_inactive_on_startup_list():
    store = store_with([
        {"pk": "operator", "sk": "wh_if", "webhook_id": "wh_if", "platform": "discord", "label": "general", "status": "active", "conversation_id": "c", "created_at": "t", "config_json": json.dumps({"bot_token": "a", "channel_id": "1"})},
        {"pk": "powerlifting", "sk": "activity#1", "webhook_id": "wh_x"},
        {"pk": "powerlifting", "sk": "wh_on", "webhook_id": "wh_on", "platform": "discord", "label": "workout", "status": "active", "conversation_id": "c", "created_at": "t", "config_json": json.dumps({"bot_token": "b", "channel_id": "2"})},
        {"pk": "powerlifting", "sk": "wh_off", "webhook_id": "wh_off", "platform": "discord", "label": "old", "status": "inactive", "conversation_id": "c", "created_at": "t", "config_json": json.dumps({"bot_token": "b", "channel_id": "3"})},
    ])
    assert [r.webhook_id for r in store.list(active_only=True)] == ["wh_on"]
    assert sorted(r.webhook_id for r in store.list()) == ["wh_off", "wh_on"]


def client_with(store, gateway):
    return TestClient(create_app(store=store, coach=FakeCoach(), directory=Directory({}), gateway=gateway))


def test_startup_opens_sockets_for_active_registrations_only():
    store = store_with()
    active = store.create(Registration(label="a", bot_token="b", channel_id="1"))
    inactive = store.create(Registration(label="b", bot_token="b", channel_id="2", status="inactive"))
    gateway = FakeGateway()
    with client_with(store, gateway):
        assert gateway.attached == [active.webhook_id]
        assert inactive.webhook_id not in gateway.attached


def test_register_requires_verified_gateway_and_starts_listening_without_returning_the_token():
    store, gateway = store_with(), FakeGateway()
    with client_with(store, gateway) as client:
        assert client.post("/v1/servers", json={"label": "workout", "bot_token": "secret", "channel_id": "42"}).status_code == 403
        response = client.post("/v1/servers", json={"label": "workout", "bot_token": "secret", "channel_id": "42"}, headers=ACCESS)
        assert response.status_code == 200
        body = response.json()
        assert body["listening"] is True and "secret" not in json.dumps(body)
        assert gateway.attached == [body["webhook_id"]]
        listed = client.get("/v1/servers", headers=ACCESS).json()
        assert "secret" not in json.dumps(listed)
        assert client.delete(f"/v1/servers/{body['webhook_id']}", headers=ACCESS).json()["status"] == "inactive"
        assert gateway.detached == [body["webhook_id"]]
        assert store.get(body["webhook_id"]).status == "inactive"


def test_linked_author_gets_the_coach_reply_in_chunks():
    coach = FakeCoach(reply="x" * 2500)
    relay = Relay(coach, Directory({"7": "person_a"}))
    channel = FakeChannel(42)
    message = FakeMessage(7, channel)
    asyncio.run(relay.answer(message, "how was my squat?"))
    assert coach.asked == [("person_a", "person_a", conversation_for("person_a", "42"), "how was my squat?")]
    assert message.replies == [chunks("x" * 2500)[0]]
    assert channel.sent == chunks("x" * 2500)[1:]


def test_unlinked_author_is_told_and_coach_is_not_called():
    coach = FakeCoach()
    message = FakeMessage(9, FakeChannel())
    asyncio.run(Relay(coach, Directory({"7": "person_a"})).answer(message, "hi"))
    assert message.replies == [NOT_LINKED] and coach.asked == []


def test_reset_clears_the_channel_conversation():
    coach = FakeCoach()
    text = asyncio.run(Relay(coach, Directory({"7": "person_a"})).reset(7, 42))
    assert coach.resets == [("person_a", conversation_for("person_a", "42"))] and "fresh" in text


def test_chunks_respect_discord_limit():
    parts = chunks("line\n" * 1000)
    assert all(len(part) <= 2000 for part in parts) and "".join(parts).count("line") == 1000


def test_gateway_shares_one_socket_per_bot_token_and_closes_it_with_the_last_channel(monkeypatch):
    from services.coach_discord.gateway import Gateway

    started = []

    async def fake_run(self, key, token):
        started.append(token)
        await asyncio.sleep(3600)

    monkeypatch.setattr(Gateway, "_run", fake_run)

    async def scenario():
        gateway = Gateway(Relay(FakeCoach(), Directory({})))
        first = Registration(label="a", bot_token="bot-1", channel_id="1")
        second = Registration(label="b", bot_token="bot-1", channel_id="2")
        other = Registration(label="c", bot_token="bot-2", channel_id="3")
        for registration in (first, second, other):
            gateway.attach(registration)
        await asyncio.sleep(0)
        assert sorted(started) == ["bot-1", "bot-2"]
        assert gateway.listening(first) and gateway.listening(second) and gateway.listening(other)
        gateway.detach(first)
        assert gateway.listening(second)
        gateway.detach(second)
        await asyncio.sleep(0)
        assert not gateway.listening(second) and gateway.listening(other)
        await gateway.close()

    asyncio.run(scenario())


def test_real_discord_client_only_relays_human_messages_in_registered_channels():
    from services.coach_discord.gateway import Gateway, token_key

    async def scenario():
        coach = FakeCoach()
        gateway = Gateway(Relay(coach, Directory({"7": "person_a"})))
        key = token_key("bot-1")
        gateway.channels[key] = {"42"}
        client = gateway._client(key)
        registered, other = FakeChannel(42), FakeChannel(99)
        human = FakeMessage(7, registered)
        human.clean_content = "squat felt slow"
        bot = FakeMessage(7, registered)
        bot.author.bot = True
        bot.clean_content = "ignore"
        elsewhere = FakeMessage(7, other)
        elsewhere.clean_content = "ignore"
        for message in (human, bot, elsewhere):
            await client.on_message(message)
        assert [asked[3] for asked in coach.asked] == ["squat felt slow"]
        await client.close()

    asyncio.run(scenario())


def test_attachments_are_forwarded_as_links():
    from types import SimpleNamespace
    from services.coach_discord.gateway import message_text

    message = SimpleNamespace(clean_content="form check", attachments=[SimpleNamespace(filename="squat.mp4", url="https://cdn.discordapp.com/a/squat.mp4")])
    assert message_text(message) == "form check\n\nAttachments:\n- squat.mp4: https://cdn.discordapp.com/a/squat.mp4"
    assert message_text(SimpleNamespace(clean_content="hi", attachments=[])) == "hi"


class FakeUserTable:
    def __init__(self, items):
        self.items = items
        self.scans = 0

    def scan(self, FilterExpression, **_):
        self.scans += 1
        wanted = FilterExpression._values[1]
        return {"Items": [item for item in self.items if item.get("discord_id") == wanted]}


def test_user_table_mapping_preserves_person_and_athlete():
    from services.coach_discord.users import UserDirectory
    table = FakeUserTable([{"pk": "sir_simpalot", "mapped_pk": "operator", "discord_id": "7"}, {"pk": "Identity#x", "discord_id": "7"}])
    coach = FakeCoach()
    relay = Relay(coach, UserDirectory("if-user", "ca-central-1", table=table))
    channel = FakeChannel(42)
    asyncio.run(relay.answer(FakeMessage(7, channel), "hi"))
    asyncio.run(relay.answer(FakeMessage(7, channel), "again"))
    assert [ask[:3] for ask in coach.asked] == [("sir_simpalot", "operator", conversation_for("operator", "42"))] * 2
    assert table.scans == 1
    asyncio.run(relay.reset(7, 42))
    assert coach.resets == [("sir_simpalot", conversation_for("operator", "42"))]


def test_ambiguous_discord_ids_do_not_select_a_person():
    from services.coach_discord.users import UserDirectory
    table = FakeUserTable([{"pk": "a", "discord_id": "7"}, {"pk": "b", "discord_id": "7"}])
    coach = FakeCoach()
    asyncio.run(Relay(coach, UserDirectory("if-user", "ca-central-1", table=table)).answer(FakeMessage(7, FakeChannel(1)), "hi"))
    assert coach.asked == []
