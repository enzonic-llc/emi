# Discord Bot with OpenWebUI AI Integration

This is a Discord bot that uses the OpenWebUI API to generate responses to chat messages.

## Prerequisites

- Python 3.7+
- Discord bot token with Message Content Intent enabled
- OpenWebUI API key

## Setup

1. Clone this repository or download the files.
2. Create a new `.env` file based on the provided template:
   ```
   DISCORD_TOKEN=your_discord_bot_token_here

   OPENWEBUI_API_URL=http://localhost:3000/api/chat/completions

   OPENWEBUI_API_KEY=your_openwebui_api_key_here

   MODEL_ID=your_model_id_here

   STATUS_MESSAGE=Online and ready to chat!

   CHANNEL_ID=your_channel_id_here
   ```

3. Edit the `system_prompt.txt` file with your desired system prompt, or use the default:
   ```
   You are a helpful assistant.
   ```

4. Install the required dependencies:
   ```
   pip install -r requirements.txt
   ```

5. Run the bot:
   ```
   python bot.py
   ```

## Customization

You can customize the bot's behavior by modifying the `bot.py` file, particularly the `get_chat_response` function and the message handling in `on_message`.

## License

This project is open source. See the LICENSE file for details.
