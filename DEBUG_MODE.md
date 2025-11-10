# Debug Mode for Testing

## Problem
When testing new features in production, you can't test the garage door functionality unless you're physically at the garage location. This makes it difficult to verify new updates remotely.

## Solution: Debug Mode

Debug mode allows specific users to **bypass location verification** so you can test from anywhere.

## How to Enable

### 1. Set Environment Variables

Add these to your `.env` file or App Engine environment variables:

**For a single debug user:**
```bash
# Enable debug mode
DEBUG_MODE=true

# Add your LINE user ID
DEBUG_USER_IDS=U1234567890abcdef
```

**For multiple debug users:**
```bash
# Enable debug mode
DEBUG_MODE=true

# Add multiple LINE user IDs (comma-separated, spaces are optional)
DEBUG_USER_IDS=U1234567890abcdef,Uanother_user_id,U999888777
```

### 2. Get Your LINE User ID

If you don't know your LINE user ID:

1. Send any message to your bot
2. Check the application logs
3. Look for lines like: `User U1234567890abcdef sent a text message`
4. Copy that user ID

### 3. Deploy to App Engine

Update your `app.yaml` with the debug settings:

**For a single debug user:**
```yaml
env_variables:
  DEBUG_MODE: "true"
  DEBUG_USER_IDS: "U1234567890abcdef"
  # ... other variables
```

**For multiple debug users:**
```yaml
env_variables:
  DEBUG_MODE: "true"
  DEBUG_USER_IDS: "U1234567890abcdef,Uanother_user_id,U999888777"
  # ... other variables
```

Then deploy:
```bash
gcloud app deploy
```

## How It Works

1. **Normal users**: Still need to verify location at garage
2. **Debug users** (when `DEBUG_MODE=true`): Can test from anywhere
3. The app logs when debug mode is used: `"Debug mode: Bypassing location verification for user ..."`

## Security Notes

⚠️ **Important Security Considerations:**

- **ALWAYS disable debug mode in production** (set `DEBUG_MODE=false`)
- Only add trusted user IDs to `DEBUG_USER_IDS`
- Monitor logs to see who's using debug mode
- Remember to turn it off after testing!

## Testing Workflow

### When You Want to Test a New Feature:

1. **Enable debug mode** (set `DEBUG_MODE=true` and add your user ID)
2. **Deploy to App Engine**
3. **Test from anywhere** - send "開關門" to your bot
4. **Verify the feature works**
5. **Disable debug mode** (set `DEBUG_MODE=false`)
6. **Deploy again** to restore normal security

## Example App Engine Configuration

```yaml
runtime: python39
entrypoint: gunicorn -b :$PORT app:app

env_variables:
  # Line Bot
  LINE_CHANNEL_ACCESS_TOKEN: "your_token"
  LINE_CHANNEL_SECRET: "your_secret"
  
  # MQTT
  MQTT_BROKER: "your_broker.emqxsl.com"
  MQTT_PORT: "8883"
  
  # Location
  PARK_LAT: "24.79155"
  PARK_LNG: "120.99442"
  MAX_DIST_KM: "0.5"
  
  # Debug Mode (ONLY for testing!)
  DEBUG_MODE: "true"
  # Single user
  DEBUG_USER_IDS: "U1234567890abcdef"
  # Or multiple users (comma-separated)
  # DEBUG_USER_IDS: "U1234567890abcdef,Uanother_user_id,U999888777"
  
  # ... other variables
```

## Alternative: Use a Staging Environment

For more secure testing, consider:

1. **Create a separate App Engine service** for staging
2. Keep debug mode enabled only on staging
3. Test there first before promoting to production
4. Never enable debug mode on production

## Quick Reference

| Variable | Purpose | Example |
|----------|---------|---------|
| `DEBUG_MODE` | Enable/disable debug mode | `true` or `false` |
| `DEBUG_USER_IDS` | Users who can bypass location verification (comma-separated for multiple users) | Single: `U1234567890abcdef`<br>Multiple: `U1234567890abcdef,Uanother_user_id,U999888777` |

---

**Remember**: Debug mode is powerful! Use it responsibly and always turn it off after testing. 🔒
