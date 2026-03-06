"""
AI Mock Interviewer — FastAPI Backend
Powered by Google Gemini + LangGraph
Deploy on HuggingFace Spaces (port 7860)
"""

import base64
import json
import os
import uuid
from io import BytesIO
from typing import Annotated, Any, Dict, List, Literal, Optional, Tuple, TypedDict, Union

import pandas as pd
from dotenv import load_dotenv
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from google import genai
from google.genai import types
from google.api_core import retry
from jinja2 import Template
from langchain_core.messages import BaseMessage
from langchain_core.messages.ai import AIMessage
from langchain_core.messages.human import HumanMessage
from langchain_core.messages.system import SystemMessage
from langchain_core.messages.tool import ToolMessage
from langchain_core.runnables import Runnable
from langchain_core.tools import BaseTool, tool
from langchain_google_genai import ChatGoogleGenerativeAI
from langgraph.graph import END, START, StateGraph
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from pydantic import BaseModel, Field

load_dotenv()

def extract_text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = [p["text"] for p in content if isinstance(p, dict) and p.get("type") == "text"]
        return " ".join(parts) if parts else ""
    return str(content)


app = FastAPI(
    title="AI Mock Interviewer API",
    description="Google Gemini + LangGraph powered technical interview simulator",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],        # Restrict to your Vercel domain in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_PATH = os.path.join(BASE_DIR, "data.json")

try:
    df = pd.read_json(DATA_PATH)
    print(f"Loaded {len(df)} questions from data.json")
except Exception as e:
    print(f"ERROR loading data.json: {e}")
    df = pd.DataFrame()

_client_cache: Dict[str, Any] = {}

def get_api_key(user_key: str = "") -> str:
    key = user_key or os.environ.get("GOOGLE_API_KEY", "")
    if not key:
        raise ValueError("No Gemini API key provided. Please enter your API key.")
    return key

def get_client(user_key: str = ""):
    key = get_api_key(user_key)
    if key not in _client_cache:
        _client_cache[key] = genai.Client(api_key=key)
        is_retriable = lambda e: isinstance(e, genai.errors.APIError) and e.code in {429, 503}
        if not hasattr(genai.models.Models.generate_content, "__wrapped__"):
            genai.models.Models.generate_content = retry.Retry(predicate=is_retriable)(
                genai.models.Models.generate_content
            )
    return _client_cache[key]

INTERVIEWER_SYSTEM_PROMPT = """
COMPANY NAME: "Mock Technologie Inc."
You are a technical interviewer and an expert in software engineering, technical interviewing, and pedagogical best practices.
Your primary goal is to evaluate a candidate's technical skills, problem-solving abilities, and relevant experience.
You should keep the candidate actively engaged and progressing through the given problem.
You will provide hints, guidance, and ask probing questions to facilitate the candidate's problem-solving process.
You are designed to be supportive, encouraging, and focused on helping the candidate demonstrate their abilities.

You should ask user to choose question for the technical interview. User can choose specific question or a random one.
You CANNOT start the interview if you have not received an interview question.
You should take questions ONLY from the question database using tools. Do NOT make up questions!
You should ask the candidate to confirm the selected question before starting.
You should ask the candidate to confirm if they want to end the interview.
Only ask probing questions or give hints if the candidate is struggling.

**I. Core Principles:**
- Facilitating Problem-Solving: Guide the candidate, don't solve it for them.
- Encouraging Communication: Prompt the candidate to explain their thought process.
- Providing Strategic Hints: Offer hints in a graduated manner (Level 1 → Level 2 → Level 3).
- Positive and Supportive Tone: Create a comfortable environment.

**II. Interview Execution:**
- Ask clarifying questions before coding begins.
- Prompt the candidate to "think out loud."
- Hint levels: Level 1 (general), Level 2 (specific), Level 3 (code snippet - sparingly).
- If completely stuck, redirect to a simpler sub-problem.

**III. Whiteboard Input:**
If a whiteboard image description is provided, seamlessly integrate your understanding into your response.
Don't create a separate "Whiteboard Analysis" section — weave it naturally into the dialogue.
If the whiteboard content is unrelated to the problem, say so clearly.

**IV. Output Format:**
Respond conversationally. Include probing questions, strategic hints, or guiding suggestions as needed.

**Example Interactions:**

Example 1 - Candidate slightly stuck:
Candidate: "I'm trying to find pairs efficiently. Maybe sort the array first?"
Interviewer: "Sorting is interesting. What's the time complexity, and how would you use the sorted array to find the pair?"

Example 2 - Small logic error in code:
Candidate: (shares hash map code with a bug)
Interviewer: "Let's trace it with nums=[3,2,4] and target=6. What happens when i=0 and nums[i]=3? What's checked and what's added?"
"""

WELCOME_MSG = """Hello! I'm a technical interviewer for Mock Technologie Inc. I'm here to help you demonstrate your software engineering skills.

To start, please choose a question for the technical interview. You can either:
- Pick a **specific topic and difficulty** (e.g. "Give me a medium array problem")
- Ask for a **random question**
- Ask me to **list available topics**

What would you prefer?"""

CANDIDATE_EVALUATION_PROMPT = """
Your Role: You are an experienced Technical Hiring Manager. Evaluate the candidate based solely on the provided interview transcript.

Evaluation Criteria:
1. Technical Competence: Problem understanding, algorithm design, coding logic, edge cases, debugging
2. Problem-Solving & Critical Thinking: Systematic approach, adaptability, optimization awareness
3. Communication & Collaboration: Clarity, active listening, asking questions, receiving feedback

Required Output (JSON):
- overallSummary: 2-3 sentence overview + high-level recommendation
- strengths: List of 5 strengths with evidence from transcript
- areasForDevelopment: List of 5+ weaknesses with evidence
- detailedAnalysis: technicalCompetence, problemSolvingCriticalThinking, communicationCollaboration (5+ sentences each)
- finalRecommendation: recommendation (Strong Hire/Hire/Lean Hire/No Hire/Needs Further Discussion) + justification
- topicsToLearn: List of areas with descriptions targeting weaknesses

Guidelines:
- Base evaluation strictly on the transcript. Be objective. Cite specific examples.
- Avoid vague evidence like "nums[i]" — use meaningful excerpts.

{question}

{transcript}

{code}
"""

RESOURCES_SEARCH_PROMPT = """
You are an expert learning advisor providing recommendations based on a technical interview evaluation.

Interview Context:
- Question Asked: {question}
- Language Used: {language}
- Expert Evaluation Summary: {analytics}
- Key Topics for Learning: {topics}

Your Task:
Generate a concise, actionable learning plan using search results.
- Start DIRECTLY with recommendations. No preamble like "Okay, based on..."
- Do NOT list URLs in your text — citations are added automatically.
- Use search tool to find current relevant resources.
- Structure clearly with bullet points.
"""

DESCRIBE_IMAGE_PROMPT = """
Given the transcript of a technical interview, analyze the provided whiteboard image.
Describe its content and relevance to the ongoing discussion or code.
Be concise — only provide what's necessary.

{transcript}
"""

REPORT_TEMPLATE = """

---

{{ evaluation.overall_summary }}

---

**Recommendation:** {{ evaluation.final_recommendation.recommendation }}

**Justification:** {{ evaluation.final_recommendation.justification }}

---

{% if evaluation.strengths %}
{% for s in evaluation.strengths %}
* **{{ s.point }}**
  * *Evidence:* {{ s.evidence }}
{% endfor %}
{% else %}
* No specific strengths noted.
{% endif %}

---

{% if evaluation.areas_for_development %}
{% for a in evaluation.areas_for_development %}
* **{{ a.point }}**
  * *Evidence:* {{ a.evidence }}
{% endfor %}
{% else %}
* No specific areas noted.
{% endif %}

---

{{ evaluation.detailed_analysis.technical_competence }}

{{ evaluation.detailed_analysis.problem_solving_critical_thinking }}

{{ evaluation.detailed_analysis.communication_collaboration }}

---

{{ recommendations | default("No specific learning recommendations were generated.") }}

---
"""

class StrengthItem(BaseModel):
    point: str = Field(..., description="Concise strength statement")
    evidence: str = Field(..., description="Evidence from transcript")

class AreaForDevelopmentItem(BaseModel):
    point: str = Field(..., description="Concise weakness statement")
    evidence: str = Field(..., description="Evidence from transcript")

class DetailedAnalysis(BaseModel):
    technical_competence: str = Field(..., alias="technicalCompetence")
    problem_solving_critical_thinking: str = Field(..., alias="problemSolvingCriticalThinking")
    communication_collaboration: str = Field(..., alias="communicationCollaboration")
    class Config:
        validate_by_name = True

class FinalRecommendation(BaseModel):
    recommendation: Literal["Strong Hire", "Hire", "Lean Hire", "No Hire", "Needs Further Discussion"]
    justification: str

class TopicsToLearn(BaseModel):
    area: str
    description: str

class EvaluationOutput(BaseModel):
    overall_summary: str = Field(..., alias="overallSummary")
    strengths: List[StrengthItem]
    areas_for_development: List[AreaForDevelopmentItem] = Field(..., alias="areasForDevelopment")
    detailed_analysis: DetailedAnalysis = Field(..., alias="detailedAnalysis")
    final_recommendation: FinalRecommendation = Field(..., alias="finalRecommendation")
    topics_to_learn: List[TopicsToLearn] = Field(..., alias="topicsToLearn")
    class Config:
        validate_by_name = True

class InterviewState(TypedDict):
    messages: Annotated[list, add_messages]
    question: str
    code: str
    report: str
    finished: bool
    api_key: str

DIFFICULTY = tuple(df.difficulty.unique().tolist()) if not df.empty else ("Easy", "Medium", "Hard")
TOPICS = tuple(df.topic.unique().tolist()) if not df.empty else ("Array Manipulation",)
IDS = df.id.apply(str).tolist() if not df.empty else []

class ListQuestionArgs(BaseModel):
    category: Literal[TOPICS] = Field(description="Topic category to filter by")
    difficulty: Literal[DIFFICULTY] = Field(description="Difficulty level: Easy, Medium, or Hard")

class SelectQuestionArgs(BaseModel):
    ID: Literal[tuple(IDS)] = Field(description="Unique ID of the question to select")

@tool(args_schema=SelectQuestionArgs)
def select_question(ID: str) -> str:
    """Selects a question by ID and loads it for the interview.
    ALWAYS use this tool when the candidate confirms their question choice.
    The interview can ONLY begin after this tool is called.
    """

@tool(args_schema=ListQuestionArgs)
def list_questions(category: str, difficulty: str) -> Union[str, List[str]]:
    """Lists available questions filtered by topic category and difficulty level.
    Returns up to 5 matching questions with their IDs and names.
    """
    filtered = df[
        (df["topic"].str.lower() == category.lower()) &
        (df["difficulty"].str.lower() == difficulty.lower())
    ]
    if filtered.empty:
        return f"No questions found for topic='{category}' and difficulty='{difficulty}'. Try different filters."
    sample = filtered.sample(n=min(len(filtered), 5))
    return [f"ID: {row.id} | {row.problem_name}" for _, row in sample[["id", "problem_name"]].iterrows()]

@tool
def get_random_problem() -> str:
    """Selects a random question from the database and returns its ID and name."""
    try:
        row = df.sample(n=1).iloc[0]
        return f"ID: {row.id} | {row.problem_name} | Difficulty: {row.difficulty} | Topic: {row.topic}"
    except Exception as e:
        return f"Error selecting random problem: {e}"

@tool
def get_difficulty_levels() -> List[str]:
    """Returns all available difficulty levels in the question database."""
    return df.difficulty.unique().tolist()

@tool
def get_topic_categories() -> List[str]:
    """Returns all available topic categories in the question database."""
    return df.topic.unique().tolist()

@tool
def end_interview() -> bool:
    """Ends the interview session and triggers the evaluation report generation.
    Use this ONLY when the candidate confirms they want to end the interview.
    """

_llm_cache: Dict[str, Any] = {}

def get_llm(user_key: str = ""):
    key = get_api_key(user_key)
    if key not in _llm_cache:
        llm = ChatGoogleGenerativeAI(model="gemini-1.5-flash", google_api_key=key)
        _llm_cache[key] = (llm, llm.bind_tools(auto_tools + interview_tools))
    return _llm_cache[key]

auto_tools: List[BaseTool] = [get_difficulty_levels, get_topic_categories, get_random_problem, list_questions]
tool_node = ToolNode(auto_tools)

interview_tools: List[BaseTool] = [select_question, end_interview]

def get_interview_transcript(messages: List[BaseMessage], api_key: str = "") -> str:
    """Converts message history to a readable transcript string.
    Handles text, code, and whiteboard image descriptions.
    """
    transcript = ""
    for message in messages:
        if isinstance(message, AIMessage) and message.content:
            content = extract_text(message.content)
            transcript += f"Interviewer: {content}\n\n"

        elif isinstance(message, HumanMessage):
            text = ""
            for part in message.content:
                text += part.get("text", "") + "\n"
                if image_data := part.get("image_url"):
                    try:
                        response = get_client(api_key).models.generate_content(
                            model="gemini-1.5-flash",
                            contents=[DESCRIBE_IMAGE_PROMPT.format(transcript=transcript), image_data.get("url")],
                        )
                        text += f"[Whiteboard description: {response.text}]\n"
                    except Exception as e:
                        text += f"[Whiteboard image could not be described: {e}]\n"
            transcript += f"Candidate: {text}\n\n"
    return transcript

def get_data_for_search(evaluation_response) -> Tuple[str, str]:
    """Extracts analytics text and topics list from evaluation for the learning plan."""
    analytics = ""
    for theme, desc in evaluation_response.parsed.detailed_analysis:
        analytics += f"{theme}: {desc}\n\n"

    topics = ""
    for item in evaluation_response.parsed.topics_to_learn:
        topics += f"{item.area}: {item.description}\n\n"

    return analytics, topics

def get_learning_resources(question: str, analytics: str, topics: str, api_key: str = "", language: str = "Python") -> str:
    """Uses Gemini with Google Search grounding to generate a personalized learning plan."""
    config = types.GenerateContentConfig(
        tools=[types.Tool(google_search=types.GoogleSearch())]
    )
    rc = None
    for attempt in range(5):
        try:
            response = get_client(api_key).models.generate_content(
                model="gemini-1.5-flash",
                contents=RESOURCES_SEARCH_PROMPT.format(
                    question=question, analytics=analytics, topics=topics, language=language
                ),
                config=config,
            )
            rc = response.candidates[0]
            if (rc.grounding_metadata
                    and rc.grounding_metadata.grounding_supports
                    and rc.grounding_metadata.grounding_chunks
                    and rc.content.parts
                    and rc.content.parts[0].text):
                break
            print(f"Grounding attempt {attempt + 1}: no metadata, retrying...")
        except Exception as e:
            print(f"Grounding attempt {attempt + 1} error: {e}")

    if not rc or not rc.grounding_metadata:
        fallback_text = "\n".join(p.text for p in rc.content.parts) if rc else ""
        return f"*Could not retrieve grounded recommendations.*\n\n{fallback_text}"

    parts = []
    generated_text = "\n".join(p.text for p in rc.content.parts)
    last_idx = 0

    for support in sorted(rc.grounding_metadata.grounding_supports, key=lambda s: s.segment.start_index):
        parts.append(generated_text[last_idx:support.segment.start_index])
        parts.append(generated_text[support.segment.start_index:support.segment.end_index])
        for i in sorted(set(support.grounding_chunk_indices)):
            parts.append(f"<sup>[{i+1}]</sup>")
        last_idx = support.segment.end_index

    parts.append(generated_text[last_idx:])
    parts.append("\n\n### Sources\n\n")
    for i, chunk in enumerate(rc.grounding_metadata.grounding_chunks, start=1):
        title = chunk.web.title or "Reference"
        uri = chunk.web.uri or "#"
        parts.append(f"{i}. [{title}]({uri})\n")

    return "".join(parts)

def chatbot_with_tools(state: InterviewState) -> InterviewState:
    """Main LLM node — generates the next interviewer response or tool call."""
    messages = state["messages"]
    system_and_messages = [SystemMessage(content=INTERVIEWER_SYSTEM_PROMPT)] + messages

    if not messages:
        ai_message = AIMessage(content=WELCOME_MSG)
    else:
        api_key = state.get("api_key", "")
        print(f"DEBUG chatbot: api_key_present={bool(api_key)}, msg_count={len(messages)}")
        _, llm_with_tools = get_llm(api_key)
        ai_message = llm_with_tools.invoke(system_and_messages)

    return state | {"messages": [ai_message]}

def question_selection_node(state: InterviewState) -> InterviewState:
    """Handles the select_question tool call — loads question content into state."""
    tool_msg: AIMessage = state["messages"][-1]
    outbound_msgs = []
    question_content = state.get("question", "")
    question_code = state.get("code", "")

    for tool_call in tool_msg.tool_calls:
        if tool_call["name"] == "select_question":
            ID = int(tool_call["args"]["ID"])
            row = df[df.id == ID].iloc[0]
            question_content = row.content
            question_code = row.code
            response = (
                f"Question loaded. Please present a summarized version of this problem to the candidate:\n\n"
                f"{question_content}\n\nStarter code:\n{question_code}"
            )
        else:
            raise NotImplementedError(f"Unknown tool: {tool_call['name']}")

        outbound_msgs.append(ToolMessage(
            content=response,
            name=tool_call["name"],
            tool_call_id=tool_call["id"],
        ))

    return state | {"messages": outbound_msgs, "question": question_content, "code": question_code}

def finish_interview_node(state: InterviewState) -> InterviewState:
    """Handles the end_interview tool call — sets finished flag."""
    tool_msg: AIMessage = state["messages"][-1]
    outbound_msgs = []

    for tool_call in tool_msg.tool_calls:
        if tool_call["name"] == "end_interview":
            response = "Say goodbye warmly to the candidate and let them know their evaluation report is being prepared."
        else:
            raise NotImplementedError(f"Unknown tool: {tool_call['name']}")

        outbound_msgs.append(ToolMessage(
            content=response,
            name=tool_call["name"],
            tool_call_id=tool_call["id"],
        ))

    return state | {"messages": outbound_msgs, "finished": True}

def create_report_node(state: InterviewState) -> InterviewState:
    """Generates the full evaluation report using structured output + grounding."""
    question = state.get("question", "")
    if not question or "not been selected" in question:
        return state | {"report": "Report cannot be generated — no question was selected."}

    messages = state.get("messages", [])
    transcript = get_interview_transcript(messages, api_key=state.get("api_key", ""))
    code = state.get("code", "")

    try:
        eval_response = get_client(state.get("api_key", "")).models.generate_content(
            model="gemini-1.5-flash",
            contents=CANDIDATE_EVALUATION_PROMPT.format(
                question=question, transcript=transcript, code=code
            ),
            config={
                "response_mime_type": "application/json",
                "response_schema": EvaluationOutput,
            },
        )
        evaluation = eval_response.parsed
    except Exception as e:
        print(f"Evaluation generation error: {e}")
        return state | {"report": f"Error generating evaluation: {e}"}

    analytics, topics = get_data_for_search(eval_response)
    recommendations = get_learning_resources(question, analytics, topics, api_key=state.get("api_key", ""))

    report_md = Template(REPORT_TEMPLATE).render(
        evaluation=evaluation,
        recommendations=recommendations,
    )

    return state | {"report": report_md}

def maybe_route_to_tools(
    state: InterviewState,
) -> Literal["tools", "question selection", "end interview", "__end__"]:
    """Routing function — decides which node to go to after the chatbot."""
    messages = state.get("messages", [])
    if not messages:
        raise ValueError("No messages in state")

    last = messages[-1]
    if not (hasattr(last, "tool_calls") and last.tool_calls):
        return "__end__"

    tool_names = [t["name"] for t in last.tool_calls]

    if any(n in tool_node.tools_by_name for n in tool_names):
        return "tools"
    elif "select_question" in tool_names:
        return "question selection"
    elif "end_interview" in tool_names:
        return "end interview"
    return "__end__"

graph_builder = StateGraph(InterviewState)

graph_builder.add_node("chatbot", chatbot_with_tools)
graph_builder.add_node("tools", tool_node)
graph_builder.add_node("question selection", question_selection_node)
graph_builder.add_node("end interview", finish_interview_node)
graph_builder.add_node("create report", create_report_node)

graph_builder.add_edge(START, "chatbot")
graph_builder.add_conditional_edges("chatbot", maybe_route_to_tools)
graph_builder.add_edge("tools", "chatbot")
graph_builder.add_edge("question selection", "chatbot")
graph_builder.add_edge("end interview", "create report")
graph_builder.add_edge("create report", "__end__")

interviewer_graph = graph_builder.compile()
print("LangGraph compiled successfully.")

sessions: Dict[str, Dict[str, Any]] = {}

class StartSessionResponse(BaseModel):
    session_id: str
    message: str

class SendMessageRequest(BaseModel):
    session_id: str
    message: str = ""
    code: str = ""
    code_changed: bool = False
    image_base64: Optional[str] = None
    api_key: Optional[str] = None  # base64-encoded PNG from whiteboard

class SendMessageResponse(BaseModel):
    message: str
    problem: str
    code: str
    finished: bool
    report: Optional[str] = None

class SessionInfoResponse(BaseModel):
    session_id: str
    problem: str
    code: str
    finished: bool

@app.get("/", tags=["Health"])
def root():
    """Health check endpoint."""
    return {
        "status": "ok",
        "service": "AI Mock Interviewer API",
        "version": "1.0.0",
        "questions_loaded": len(df),
    }

class StartSessionRequest(BaseModel):
    api_key: Optional[str] = None

@app.post("/api/session/start", response_model=StartSessionResponse, tags=["Session"])
def start_session(req: StartSessionRequest = StartSessionRequest()):
    """
    Start a new interview session.
    Returns a session_id and the AI's welcome message.
    """
    session_id = str(uuid.uuid4())
    initial_state: Dict[str, Any] = {
        "messages": [],
        "question": "Problem has not been selected yet",
        "code": "# Your solution here\n",
        "report": "",
        "finished": False,
        "api_key": req.api_key or "",
    }

    try:
        new_state = interviewer_graph.invoke(initial_state)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to initialize graph: {e}")

    welcome = WELCOME_MSG
    for msg in reversed(new_state.get("messages", [])):
        if isinstance(msg, AIMessage):
            welcome = extract_text(msg.content)
            break

    new_state["api_key"] = req.api_key or ""
    sessions[session_id] = new_state
    return StartSessionResponse(session_id=session_id, message=welcome)

@app.post("/api/chat", response_model=SendMessageResponse, tags=["Interview"])
def chat(req: SendMessageRequest):
    """
    Send a message, code update, or whiteboard image to the AI interviewer.
    Returns the AI's response and updated state.
    """
    if req.session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found. Please start a new session.")

    state = sessions[req.session_id]

    if state.get("finished"):
        return SendMessageResponse(
            message="The interview has ended. Your report is ready below.",
            problem=state.get("question", ""),
            code=state.get("code", ""),
            finished=True,
            report=state.get("report", ""),
        )

    content: List[Dict[str, Any]] = []

    if req.message:
        content.append({"type": "text", "text": req.message})

    if req.code_changed and req.code:
        content.append({"type": "text", "text": f"\nMy current code:\n```python\n{req.code}\n```"})

    if req.image_base64:
        content.append({"type": "text", "text": "Here is a screenshot of my whiteboard:"})
        content.append({
            "type": "image_url",
            "image_url": {"url": f"data:image/png;base64,{req.image_base64}"},
        })

    if not content:
        return SendMessageResponse(
            message="Please provide a message, code update, or whiteboard drawing.",
            problem=state.get("question", ""),
            code=state.get("code", ""),
            finished=False,
        )

    current_messages = list(state.get("messages", []))
    current_messages.append(HumanMessage(content=content))

    user_key = req.api_key or state.get("api_key", "")
    print(f"DEBUG: session_id={req.session_id}, user_key_present={bool(user_key)}, message={req.message[:50] if req.message else ''}")
    graph_input: Dict[str, Any] = {
        "messages": current_messages,
        "question": state.get("question", ""),
        "code": req.code if req.code_changed else state.get("code", ""),
        "report": state.get("report", ""),
        "finished": False,
        "api_key": user_key,
    }

    try:
        new_state = interviewer_graph.invoke(graph_input)
    except Exception as e:
        import traceback
        print("=== CHAT ERROR ===")
        print(traceback.format_exc())
        print("==================")
        err = str(e)
        if "429" in err or "RESOURCE_EXHAUSTED" in err:
            return SendMessageResponse(
                message="The AI is receiving too many requests right now. Please wait a few seconds and try again.",
                problem=state.get("question", ""),
                code=state.get("code", ""),
                finished=False,
            )
        if "quota" in err.lower():
            return SendMessageResponse(
                message="API quota exceeded. Please wait a minute before sending another message.",
                problem=state.get("question", ""),
                code=state.get("code", ""),
                finished=False,
            )
        raise HTTPException(status_code=500, detail=f"Interview graph error: {traceback.format_exc()}")

    sessions[req.session_id] = new_state

    ai_response = "Processing..."
    for msg in reversed(new_state.get("messages", [])):
        if isinstance(msg, AIMessage):
            ai_response = extract_text(msg.content)
            break
        elif isinstance(msg, ToolMessage) and msg.name == "end_interview":
            ai_response = "Thank you for your time! The interview has ended. Your evaluation report is being prepared..."
            break

    finished = new_state.get("finished", False)
    if finished:
        ai_response += "\n\n**Your evaluation report is ready below.**"

    return SendMessageResponse(
        message=ai_response,
        problem=new_state.get("question", ""),
        code=new_state.get("code", ""),
        finished=finished,
        report=new_state.get("report") if finished else None,
    )

@app.get("/api/session/{session_id}", response_model=SessionInfoResponse, tags=["Session"])
def get_session(session_id: str):
    """Get current session state (problem, code, finished status)."""
    if session_id not in sessions:
        raise HTTPException(status_code=404, detail="Session not found.")
    state = sessions[session_id]
    return SessionInfoResponse(
        session_id=session_id,
        problem=state.get("question", ""),
        code=state.get("code", ""),
        finished=state.get("finished", False),
    )

@app.delete("/api/session/{session_id}", tags=["Session"])
def delete_session(session_id: str):
    """Delete a session and free memory."""
    sessions.pop(session_id, None)
    return {"status": "deleted", "session_id": session_id}

@app.get("/api/questions/topics", tags=["Questions"])
def get_topics():
    """List all available question topics."""
    return {"topics": df.topic.unique().tolist()}

@app.get("/api/questions/difficulties", tags=["Questions"])
def get_difficulties():
    """List all available difficulty levels."""
    return {"difficulties": df.difficulty.unique().tolist()}

@app.get("/api/questions", tags=["Questions"])
def list_all_questions(topic: Optional[str] = None, difficulty: Optional[str] = None):
    """List questions with optional topic and difficulty filters."""
    filtered = df.copy()
    if topic:
        filtered = filtered[filtered["topic"].str.lower() == topic.lower()]
    if difficulty:
        filtered = filtered[filtered["difficulty"].str.lower() == difficulty.lower()]
    return {
        "count": len(filtered),
        "questions": filtered[["id", "problem_name", "topic", "difficulty", "link"]].to_dict(orient="records"),
    }