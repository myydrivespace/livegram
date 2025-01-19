import logging
logging.basicConfig(level=logging.INFO)

from pyrogram import Client, filters
from pyrogram.types import Message, ReplyKeyboardMarkup, KeyboardButton
from pymongo import MongoClient

from config import (
    API_ID,
    API_HASH,
    BOT_TOKEN,
    ADMIN_ID,
    GROUP_CHAT_ID,
    MONGO_URI
)

# Initialize the bot client
app = Client(
    "livegram_bot",
    api_id=API_ID,
    api_hash=API_HASH,
    bot_token=BOT_TOKEN
)

# Connect to MongoDB
mongo_client = MongoClient(MONGO_URI)
db = mongo_client["livegram"]
user_collection = db["users"]
message_mapping_collection = db["message_mapping"]

@app.on_message(filters.command("start") & filters.private)
async def start(client, message: Message):
    """Show the menu with ReplyKeyboardMarkup and collect user ID."""
    user_id = message.from_user.id
    user_name = message.from_user.first_name or "Unknown"

    if user_id == ADMIN_ID:
        await message.reply("Welcome, Admin! You have access to admin commands. Use /broadcast to send messages to users.")
        return

    user_collection.update_one(
        {"_id": user_id},
        {"$set": {"name": user_name, "active_option": None}},
        upsert=True
    )

    reply_markup = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("Admin Support"), 
                KeyboardButton("Sponsorship"),
                KeyboardButton("Report Scam")
            ],
        ],
        resize_keyboard=True,
        one_time_keyboard=False
    )
    await message.reply("Welcome! Choose an option below:", reply_markup=reply_markup)


@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_message(client, message: Message):
    if not message.reply_to_message:
        await message.reply("Please reply to a message to broadcast it.")
        return

    success_count = 0
    failure_count = 0

    broadcast_message_id = message.reply_to_message.id

    users = user_collection.find()

    if not users:
        await message.reply("No users found to broadcast the message.")
        return

    for user in users:
        user_id = user["_id"]
        try:
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=broadcast_message_id
            )
            success_count += 1
        except Exception as e:
            print(f"Failed to send message to {user_id}: {e}")
            failure_count += 1

    await message.reply(f"Broadcast completed: {success_count} successes, {failure_count} failures.")


@app.on_message(filters.private & ~filters.bot)
async def handle_user_message(client, message: Message):
    user_id = message.from_user.id

    if user_id == ADMIN_ID and message.text in ["Admin Support", "Sponsorship", "Report Scam"]:
        await message.reply("You are the admin. These menu options are for users only.")
        return

    if user_id == ADMIN_ID:
        return

    user = user_collection.find_one({"_id": user_id})
    if not user:
        await message.reply("Please use /start to begin.")
        return

    if message.text == "Admin Support":
        user_collection.update_one({"_id": user_id}, {"$set": {"active_option": "admin_support"}})
        await message.reply("Thank you for contacting us! We’ve received your message and will get back to you as soon as possible ")
    elif message.text == "Sponsorship":
        user_collection.update_one({"_id": user_id}, {"$set": {"active_option": "sponsorship"}})
        await message.reply("Thank you for reaching out! Please share your sponsorship details")
    elif message.text == "Report Scam":
        user_collection.update_one({"_id": user_id}, {"$set": {"active_option": "report_scam"}})
        await message.reply("Please provide all the necessary details and proof of the scam, such as screenshots, payment receipts, or chat history. This will help us review the matter and take appropriate action")
    else:
        active_option = user.get("active_option")
        thread_id = None

        if active_option == "admin_support":
            thread_id = 48
        elif active_option == "sponsorship":
            thread_id = 45
        elif active_option == "report_scam":
            thread_id = 46
        
        if thread_id:
            forwarded_message = await client.forward_messages(
                chat_id=GROUP_CHAT_ID,
                from_chat_id=message.chat.id,
                message_thread_id=thread_id,
                message_ids=message.id
            )

            message_mapping_collection.insert_one({
                "forwarded_message_id": forwarded_message.id,
                "original_user_id": user_id
            })
        else:
            await message.reply("Please select an option (Admin Support, Sponsorship, or Report Scam) from the menu to get started.")


@app.on_message(filters.chat(GROUP_CHAT_ID) & filters.reply)
async def forward_reply_to_user(client, message: Message):
    """Forward admin replies in the group back to the user."""
    if message.reply_to_message:
        mapping = message_mapping_collection.find_one({"forwarded_message_id": message.reply_to_message.id})
        if mapping:
            user_id = mapping["original_user_id"]
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.id
            )

@app.on_message(filters.private & filters.reply & filters.user(ADMIN_ID))
async def handle_admin_reply(client, message: Message):
    """Forward admin's replies to the original user."""
    if message.reply_to_message:
        mapping = message_mapping_collection.find_one({"forwarded_message_id": message.reply_to_message.id})
        if mapping:
            user_id = mapping["original_user_id"]
            await client.copy_message(
                chat_id=user_id,
                from_chat_id=message.chat.id,
                message_id=message.id
            )

if __name__ == "__main__":
    app.run()
