---
title: Mock Technical Interviewer
emoji: 🐠
colorFrom: blue
colorTo: blue
sdk: docker
pinned: false
app_port: 7860
---

# AI Mock Interviewer

An AI-powered mock technical interview platform. You talk to an AI interviewer, solve coding problems, draw on a whiteboard, and at the end receive a detailed evaluation report with personalized learning recommendations.

Built with Google Gemini, LangGraph, FastAPI, and React.

---

## What Is This Project

Most people prepare for technical interviews by solving problems alone. But real interviews are conversations — you need to think out loud, explain your approach, handle hints, and write code under pressure. This project simulates exactly that.

The AI acts as a real technical interviewer. It asks you a coding question, listens to your explanation, gives hints when you are stuck, reviews your code, and after the interview generates a full report on how you performed and what you should study next.

---

## Features

- AI interviewer that asks questions, gives hints, and evaluates your answers
- Coding questions from a LeetCode-style database, filterable by topic and difficulty
- Built-in code editor where you write and submit your solution
- Interactive whiteboard where you can draw diagrams and the AI understands them
- Full evaluation report at the end covering problem-solving, code quality, and communication
- Personalized learning resources based on your weak areas, pulled from Google Search

---

## How It Works — Simple Version

1. You open the app and the AI greets you
2. You pick a coding question by topic, difficulty, or ask for a random one
3. The AI presents the question and you start solving it
4. As you work, you can type your thoughts, write code, or draw on the whiteboard
5. The AI responds like a real interviewer — asking follow-up questions or giving hints
6. When you are done, you tell the AI to end the interview
7. The AI generates a detailed report and learning plan for you

---

## How It Works — Technical Version

### Architecture

The app has two parts — a backend and a frontend.

The backend is a FastAPI server that contains all the AI logic. It uses LangGraph to manage the interview as a stateful graph. Each user gets a session with its own conversation history, active question, and code. The frontend is a React app that provides the chat interface, code editor, and whiteboard.

### LangGraph Agent

The interview flow is a directed graph with these nodes:

- **chatbot** — calls Gemini with the full conversation history and system prompt to generate the next response
- **tools** — executes information-retrieval tools like listing questions or picking a random problem
- **question selection** — a custom node that loads the chosen question into the session state
- **end interview** — a custom node that marks the session as finished
- **create report** — generates the structured evaluation and learning plan

Standard LangGraph ToolNode cannot modify state directly. That is why question selection and end interview use custom nodes — they need to update the session state, not just return a value.

### Tools Available to the AI

| Tool | What It Does |
|------|-------------|
| `get_topic_categories` | Returns all available question topics |
| `get_difficulty_levels` | Returns all difficulty levels |
| `list_questions` | Lists questions filtered by topic and difficulty |
| `get_random_problem` | Picks a random question |
| `select_question` | Loads a specific question into the session |
| `end_interview` | Ends the session and triggers report generation |

### Evaluation Report

When the interview ends, Gemini generates a structured JSON report using a Pydantic schema. This ensures the output is always consistent. The JSON is then rendered into a readable Markdown report using a Jinja2 template. The report covers:

- Overall summary and hiring recommendation
- Strengths with evidence from the transcript
- Areas for development with evidence
- Detailed analysis of technical competence, problem solving, and communication
- Personalized learning topics

### Whiteboard

The whiteboard is an HTML5 canvas. When you click Send, it is captured as a base64 PNG and sent to the backend. The backend passes it to Gemini Vision which describes the drawing in the context of the conversation. That description is then included in the AI's next response.

### Learning Resources

After evaluation, Gemini is called again with Google Search enabled. It searches for current, relevant resources based on your identified weak areas and returns a response with automatic citations.

---

## Requirements

- Python 3.11 or higher
- Node.js 18 or higher
- A Google Gemini API key — get one free at https://aistudio.google.com/apikey
- A HuggingFace account — sign up free at https://huggingface.co
- A GitHub account — sign up free at https://github.com
- A Vercel account — sign up free at https://vercel.com

---

## Backend Files

These files make up the backend:

- `main.py` — the entire FastAPI application including all prompts, LangGraph nodes, tools, and API endpoints
- `data.json` — the question database containing LeetCode-style problems with descriptions, starter code, difficulty, topic, and companies
- `requirements.txt` — all Python packages needed to run the backend
- `Dockerfile` — instructions for building the backend as a Docker container for HuggingFace Spaces
- `README.md` — contains the HuggingFace Spaces configuration header that tells HF this is a Docker app running on port 7860

## Frontend Files

These files make up the frontend:

- `src/App.jsx` — the entire React application including home screen, chat interface, code editor, whiteboard, and report viewer
- `src/index.css` — all styles for the app
- `src/main.jsx` — the React entry point
- `index.html` — the HTML shell that loads the React app
- `vite.config.js` — Vite build configuration
- `package.json` — all JavaScript packages needed
- `.env` — environment variables, specifically the backend URL

---

## Step 1 — Set Up the Backend on HuggingFace Spaces

HuggingFace Spaces lets you host Docker apps for free. The backend runs as a Docker container there.

**Create a new Space:**
1. Go to https://huggingface.co/spaces
2. Click **Create new Space**
3. Give it a name like `ai-mock-interviewer-api`
4. Set SDK to **Docker**
5. Set Visibility to **Public**
6. Click **Create Space**

**Upload the backend files:**
1. On your Space page click **Files**
2. Click **Add file → Upload file**
3. Upload all five backend files: `main.py`, `data.json`, `requirements.txt`, `Dockerfile`, `README.md`

**Add your Gemini API key:**
1. Go to your Space **Settings**
2. Scroll to **Repository secrets**
3. Click **New secret**
4. Set Name to `GOOGLE_API_KEY`
5. Paste your Gemini API key as the value
6. Click **Save**

**Wait for it to build:**

HuggingFace will automatically build and start the backend. This takes 3 to 5 minutes. Watch the logs on the Space page. When it says **Running** your backend is live.

**Your backend URL will be:**
```
https://YOUR-HUGGINGFACE-USERNAME-ai-mock-interviewer-api.hf.space
```

**Verify it works** by opening this in your browser:
```
https://YOUR-HUGGINGFACE-USERNAME-ai-mock-interviewer-api.hf.space/docs
```
You should see an interactive API documentation page. If you see it, the backend is working correctly.

---

## Step 2 — Set Up the Frontend on Vercel

Vercel hosts the React frontend for free and automatically builds it from GitHub.

**Push frontend files to GitHub:**
```bash
git init
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/YOUR-GITHUB-USERNAME/ai-mock-interviewer-frontend.git
git push -u origin main
```

**Deploy on Vercel:**
1. Go to https://vercel.com and sign in with GitHub
2. Click **Add New Project**
3. Import your `ai-mock-interviewer-frontend` repository
4. Before clicking Deploy, scroll to **Environment Variables** and add:
   - Name: `VITE_API_URL`
   - Value: your HuggingFace backend URL from Step 1
5. Click **Deploy**

Vercel will build and deploy in about a minute. Your frontend will be live at:
```
https://ai-mock-interviewer-frontend.vercel.app
```

---

## Step 3 — Use the App

1. Open your Vercel URL in the browser
2. The home screen has two fields:
   - **HuggingFace Backend URL** — your HF Space URL. A green badge confirms the connection
   - **Google Gemini API Key** — your Gemini key
3. Click **Start Interview**
4. The AI will greet you and ask you to choose a question. For example you can say:
   - "Give me a medium difficulty array problem"
   - "I want a random question"
   - "What topics are available?"
5. Once a question is selected it appears in the Problem panel on the left
6. Explain your approach in the chat, write your solution in the code editor, and use the whiteboard button to draw diagrams
7. When finished, tell the AI you want to end the interview and confirm when asked
8. Your evaluation report will appear and you can download it as a Markdown file

---

## Run Locally Without Deploying

If you want to run the project on your own machine:

```bash
# Terminal 1 — Backend
pip install -r requirements.txt
export GOOGLE_API_KEY=your_gemini_api_key
uvicorn main:app --reload --port 7860
# Runs at http://localhost:7860
# API docs at http://localhost:7860/docs

# Terminal 2 — Frontend
npm install
npm run dev
# Runs at http://localhost:5173
```

When running locally, enter `http://localhost:7860` as the backend URL on the home screen.

---

## API Reference

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/` | Health check, returns status and number of questions loaded |
| POST | `/api/session/start` | Creates a new interview session, returns session ID and welcome message |
| POST | `/api/chat` | Sends a message, code update, or whiteboard image to the AI |
| GET | `/api/session/{id}` | Returns the current state of a session |
| DELETE | `/api/session/{id}` | Deletes a session |
| GET | `/api/questions` | Lists questions, accepts optional topic and difficulty query params |
| GET | `/api/questions/topics` | Returns all available question topics |
| GET | `/api/questions/difficulties` | Returns all available difficulty levels |
| GET | `/docs` | Interactive Swagger API documentation |

---

## Limitations

- The AI reads and discusses your code but does not execute it or run it against test cases
- Sessions are stored in memory on the backend. If the HuggingFace Space restarts, active sessions are lost
- The AI provides strong consistent evaluations based on the transcript but cannot observe things like hesitation or tone the way a human interviewer can