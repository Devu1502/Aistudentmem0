# AI-Buddy Setup Guide

## Requirements

Before starting, make sure you have:

* Python 3.10 or later
* MongoDB Atlas connection string
* Qdrant Cloud API key
* OpenAI API key

---

## Setup Instructions

### Clone the Repository

```bash
git clone https://github.com/NasrinDbg/AI-Buddy.git
cd AI-Buddy
```

### Create and Activate Virtual Environment

```bash
python3 -m venv venv
source venv/bin/activate
```

### Install Required Dependencies

```bash
pip install -r requirements.txt
```

### Add Environment Variables

Create a file named `.env` in the project’s root folder and add:

```bash
MONGODB_URI="your_mongodb_connection_string"
QDRANT_API_KEY="your_qdrant_api_key"
OPENAI_API_KEY="your_openai_api_key"
ELEVENLABS_API_KEY="your_elevenlabs_api_key"
```

---

## Run the App
## Two-Terminal Setup

**Terminal 1 – Run Backend**

```bash
uvicorn app:app --reload
```

**Terminal 2 – Run Frontend**

```bash
npm install
npm start
```

---

 Once both are running, open your browser and interact with **AI-Buddy** locally.
