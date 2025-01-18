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

    # Add or update user in the database
    user_collection.update_one(
        {"_id": user_id},
        {"$set": {"name": user_name, "active_option": None}},
        upsert=True
    )

    # Create the reply keyboard
    reply_markup = ReplyKeyboardMarkup(
        [
            [
                KeyboardButton("Admin Support"), 
                KeyboardButton("Sponsorship"),
                KeyboardButton("Report Scam")
            ],
        ],
        resize_keyboard=True,  # Adjust button size
        one_time_keyboard=False  # Keep the keyboard persistent
    )
    await message.reply("Welcome! Choose an option below:", reply_markup=reply_markup)

@app.on_message(filters.private & ~filters.bot & ~filters.command("broadcast"))
async def handle_user_message(client, message: Message):
    if message.from_user.id == ADMIN_ID:
        return

    user_id = message.from_user.id
    user = user_collection.find_one({"_id": user_id})
    if not user:
        await message.reply("Please use /start to begin.")
        return

    if message.text == "Admin Support":
        # Activate Admin Support and deactivate others
        user_collection.update_one({"_id": user_id}, {"$set": {"active_option": "admin_support"}})
        await message.reply("Admin Support enabled! Send me a message, and I will forward it to the admin.")
    elif message.text == "Sponsorship":
        # Activate Sponsorship and deactivate others
        user_collection.update_one({"_id": user_id}, {"$set": {"active_option": "sponsorship"}})
        await message.reply("Sponsorship option enabled! Send me a message, and I will forward it to the admin.")
    elif message.text == "Report Scam":
        # Activate Report Scam and deactivate others
        user_collection.update_one({"_id": user_id}, {"$set": {"active_option": "report_scam"}})
        await message.reply("Report Scam option enabled! Send me a message, and I will forward it to the admin.")
    else:
        # Check the active option for the user
        active_option = user.get("active_option")
        if active_option:
            extra_message = ""
            if active_option == "admin_support":
                extra_message = f"#Admin_Support\nMessage From: {message.from_user.first_name or 'Unknown'}\nUser Id: {user_id}"
            elif active_option == "sponsorship":
                extra_message = f"#Sponsorship\nMessage From: {message.from_user.first_name or 'Unknown'}\nUser Id: {user_id}"
            elif active_option == "report_scam":
                extra_message = f"#ReportScam\nMessage From: {message.from_user.first_name or 'Unknown'}\nUser Id: {user_id}"

            # Forward the original message to the group
            forwarded_message = await client.forward_messages(
                chat_id=GROUP_CHAT_ID,
                from_chat_id=message.chat.id,
                message_ids=message.id
            )

            # Store the mapping in the database
            message_mapping_collection.insert_one({
                "forwarded_message_id": forwarded_message.id,
                "original_user_id": user_id
            })

            # Send the extra message to the group
            if extra_message:
                await client.send_message(chat_id=GROUP_CHAT_ID, text=extra_message)
        else:
            await message.reply("Please select an option (Admin Support, Sponsorship, or Report Scam) from the menu to get started.")

@app.on_message(filters.command("broadcast") & filters.user(ADMIN_ID))
async def broadcast_message(client, message: Message):
    if not message.reply_to_message:
        await message.reply("Please reply to a message to broadcast it.")
        return

    success_count = 0
    failure_count = 0

    # Broadcast the replied-to message using copy_message
    broadcast_message_id = message.reply_to_message.id
    for user in user_collection.find():
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

    # Acknowledge the admin about the broadcast result
    await message.reply(f"Broadcast completed: {success_count} successes, {failure_count} failures.")

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
