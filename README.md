## Taplist Application

A Flask-based application to display beer taplist data from Brewers Friend API with background polling for improved performance.

### Features

- **Secure API Key Management**: API keys are stored as environment variables, not in config files
- **Background Polling**: Data is fetched in the background at configurable intervals, making the UI fast and responsive
- **Admin Authentication**: Admin panel is protected with password authentication
- **Data Caching**: Beer data is cached in memory and persisted to XML files
- **Multiple Themes**: Support for different themes and styles

### Installation

You will need to install a few required libraries:

```bash
pip install requests flask
```

### Configuration

1. **Set Environment Variables** (Recommended):
   ```bash
   export BREWERS_FRIEND_API_KEY="your_api_key_here"
   export FLASK_SECRET_KEY="your_secret_key_here"  # Optional, defaults to a basic key
   ```

2. **Admin Password**: The default admin password is "admin". Change it via the admin panel after first login.

3. **Background Polling**: Data is automatically fetched from the API in the background every hour (3600 seconds) by default. This can be configured in the admin panel.

### Running the Application

```bash
python3 taplist.py
```

Navigate to `localhost:5000` in your favorite browser.

### Admin Access

- Access the admin panel via the gear icon in the top left corner
- Default admin password: `admin` (change this immediately)
- Use `/admin/logout` to log out of the admin panel

### Security Improvements

- API keys are no longer stored in config files
- Admin panel requires authentication
- Input validation on all form fields
- Secure session management
- XML output is properly escaped

### Performance Improvements

- Background polling eliminates wait times for API calls
- Data is cached in memory for instant access
- Reduced API calls through intelligent caching
- Non-blocking user interface

### TODO

- Add more themes
- Enhanced admin features
- Database integration for larger datasets



