# AI Mock Interviewer

## Building an AI-Powered Interview Coach with Google Gemini and LangGraph

Let's face it: preparing for technical interviews is challenging. You might solve countless LeetCode problems, watch mock interviews, and rehearse answers, but something often feels missing. If you're like many aspiring developers, you might lack a reliable practice partner who can simulate real interview pressure, provide insightful feedback, and adapt to your learning pace.

That's exactly why I built an **AI Mock Technical Interviewer**—a smart, interactive coach powered by Google's Gemini AI and LangGraph.

![AI Mock Interviewer App UI](https://raw.githubusercontent.com/satheeshbhukya/AI-mock-Interviewer/main/static/firstpage.png)

## The Problem: Why Self-Prep Falls Short

Preparing for technical interviews isn't just about solving problems—it's about **thinking aloud, handling pressure, and communicating clearly**. Common struggles include:

- **Lack of Realistic Practice:** Solving problems alone ≠ explaining your approach under time constraints.
- **Limited Feedback:** Friends or peers may not always be available or provide structured critiques.
- **No Adaptive Guidance:** Real interviewers give hints when you're stuck—most practice tools don't.
- **No Whiteboarding Simulation:** Many coding interviews involve sketching ideas, but few platforms support interactive diagrams.

This project was born from my own frustrations while prepping for interviews. I wanted an AI that could **mimic a real interviewer**, offering not just questions but **coaching, hints, and detailed feedback**.

## The Solution: An AI That Interviews Like a Human

This AI interviewer isn't just a question bank—it's an interactive coach that:

1. **Conducts Realistic Interviews:** Picks questions from a curated list (no random, irrelevant problems).
2. **Guides You Like a Pro:** Offers hints when you're stuck, just like a real interviewer would.
3. **Understands Whiteboarding:** Lets you sketch solutions on a digital whiteboard (Gemini analyzes the drawing!).
4. **Remembers Context:** Uses LangGraph to track conversation history for coherent discussions.
5. **Provides Detailed Feedback:** After the interview, it generates a structured report on:
   - Problem-solving approach
   - Code quality
   - Communication skills
6. **Recommends Learning Resources:** Uses Google Search (via Gemini Grounding) to suggest study materials based on weak areas.

## How It Works: Gemini + LangGraph

### Core Technologies
- **Google Gemini:** Handles natural language interactions, image understanding (for whiteboard sketches), and feedback generation.
- **LangGraph:** Manages conversation flow, state tracking, and tool integrations.
- **Gradio:** Provides the interactive UI for coding, chatting, and drawing.

### Key Features in Action
1. **Dynamic Question Selection**
   - The AI suggests questions based on topic/difficulty.
   - Once selected, it loads the problem description and starter code.

2. **Interactive Whiteboard**
   - Sketch your approach (e.g., diagrams, pseudocode).
   - Gemini interprets the drawing and discusses it with you.

3. **Smart Hint System**
   - If you're stuck, ask for help, and the AI nudges you in the right direction.

4. **Structured Feedback Report**
   - Post-interview, Gemini analyzes your performance and generates a detailed review.

## Behind the Scenes: Challenges & Solutions

### Challenge 1: Making the AI Interview Like a Human
- **Problem:** Initially, Gemini either gave away answers too quickly or didn't guide effectively.
- **Solution:** Fine-tuned the prompts with few-shot examples to balance hints and independent thinking.

### Challenge 2: Managing Interview State
- **Problem:** The AI needed to remember the current question, code, and conversation history.
- **Solution:** Used LangGraph's stateful workflows to track context.

**Interview Flow Visualization**
<p align="center">
<img src="https://raw.githubusercontent.com/satheeshbhukya/AI-mock-Interviewer/main/static/graph-visualisation.png" alt="Interview Graph structure" width="500"/>
</p>

This required a special setup in LangGraph. The `select_question` tool itself is simple (it just defines *that* the action exists): 

```python
# Tool definition for selecting a question

class SelectQuestionArgs(BaseModel):
    """Input schema for the select_question tool."""
    ID: Literal[tuple(IDS)] = Field(description="ID of the question")

@tool(args_schema=SelectQuestionArgs)
def select_question(ID: str) -> str:
    """Shows user question with provided ID.
    ALWAYS use this tool when the candidate confirms selected question.
    You can start interview process ONLY after using this tool.
    """
    # This tool itself doesn't contain the main logic...
    pass # ...the logic happens in the custom node below
```

The *real* work happens in a custom LangGraph *node* called `question_selection_node`. This node runs *after* the AI decides to use the `select_question` tool:

```python
# Simplified logic inside the 'question_selection_node' function

def question_selection_node(state: InterviewState) -> InterviewState:
    # 1. Get the last AI message (which contains the tool call)
    tool_msg: AIMessage = state.get("messages", [])[-1]

    # 2. Loop through tool calls in that message (usually just one here)
    for tool_call in tool_msg.tool_calls:
        if tool_call["name"] == "select_question":
            # 3. Extract the Question ID the AI provided
            ID: int = int(tool_call["args"]["ID"])

            # 4. Find the question details in the question database 
            selected_question: pd.Series = df[df.id==ID].iloc[0]
            question_content = selected_question.content
            question_code = selected_question.code

            # 5. Prepare a message confirming the selection
            response = f"Okay, let's work on '{selected_question.problem_name}'. Here's the description:\n{question_content}\nInitial code:\n{question_code}"

            # Create a message containing the response for the AI
            tool_message = ToolMessage(content=response, name=tool_call["name"], tool_call_id=tool_call["id"])

    # 6. CRITICAL STEP: Update the state dictionary with the new question and code!
    # The '|' merges the old state with the new values.
    return state | {
        "messages": [tool_message], # Add the tool result message
        "question": question_content, # Update the active question
        "code": question_code         # Update the starter code
    }
```
Making these state-changing tools work correctly felt like properly wiring up the AI's brain and hands – tricky, but essential!

**Explaining LangGraph's Tool Magic (Simply):**

LangGraph provides powerful ways to structure AI interactions, but some of its abstractions, like how tools are called, can be a bit confusing at first glance, requiring a deeper dive into its underlying implementation.

Here's the simple version of how the *standard* `ToolNode` (used for tools that *don't* change the state directly, like getting the list of topics) works:

1.  You chat with the AI interviewer.
2.  Based on the conversation and its instructions (especially after using `.bind_tools(tools)` to tell the model which tools are available), the AI (Gemini) might decide it needs to use a tool. It outputs a special `AIMessage` containing `tool_calls`, like: `AIMessage(content="", tool_calls=[{"name": "get_topic_categories", "args": {}, "id": "call_123"}])`.
3.  LangGraph routes the flow to the `ToolNode`.
4.  `ToolNode` looks at the `tool_calls` in that last `AIMessage`.
5.  It finds the matching Python function (e.g., our `get_topic_categories` function decorated with `@tool`).
6.  It runs that function.
7.  It takes the result (the list of topics) and wraps it in a `ToolMessage`, linking it back to the original call ID: `ToolMessage(content=['Arrays', 'Linked Lists', ...], name='get_topic_categories', tool_call_id='call_123')`.
8.  This `ToolMessage` gets added to the state's message list.
9.  The flow usually goes back to the AI, which now sees the tool result and can form its next response, like, "Okay, we have questions on these topics: Arrays, Linked Lists..."

For tools like `select_question` that *do* need to change the state, we bypass the standard `ToolNode` and use a custom node (`question_selection_node`) as shown in the previous section.

**Surprise! The AI Gives Good Feedback?**

I was genuinely impressed by the quality of the feedback the AI generated. It didn't just say "good job" or "try harder." It pointed to specific parts of the conversation, analyzed my approach, commented on communication, and created that personalized learning plan. It highlighted things I wouldn't notice just by solving problems alone. That showed me the real value beyond just question-answering.

It also surprised me with its flexibility. I could ask "give me beginner array problems" and it would understand and use the `list_questions` tool with the right filters (`difficulty='Easy'`, `category='Array Manipulation'`). Switching questions mid-interview was also smooth, thanks to the state management and tools.

**Getting the Structured Feedback:**

To make sure the final report was consistent and easy to use, I told Gemini exactly what format to use. I defined a structure using Python's Pydantic library, like a blueprint for the report.

```python
# Example Pydantic Model (Blueprint for part of the feedback)
class StrengthItem(BaseModel):
    """Represents a single observed strength."""
    point: str = Field(..., description="Concise statement of the strength")
    evidence: str = Field(..., description="Specific examples or quotes")

class EvaluationOutput(BaseModel):
    """Root object for the complete evaluation."""
    overall_summary: str = Field(..., alias="overallSummary")
    strengths: List[StrengthItem] = Field(...)
    # ... other fields like areas_for_development, detailed_analysis, etc.
```

Then, when calling the Gemini API to generate the report, I told it to follow this blueprint:

```python
# Inside the function that generates the report (create_report_node)

evaluation_response = client.models.generate_content(
    model='gemini-2.0-flash',
    contents=CANDIDATE_EVALUATION_PROMPT.format(...), # Prompt asking for evaluation
    config={
        'response_mime_type': 'application/json', # Tell it we want JSON
        'response_schema': EvaluationOutput,     # Tell it the *exact* structure/blueprint
    },
)
# Now, evaluation_response.parsed contains the data neatly structured
evaluation_data: EvaluationOutput = evaluation_response.parsed
```
This ensures the output is always organized the same way, making it reliable.


### Limitations and What's Next

This is a great start, but it's not perfect:

*   **It Can't *Run* Your Code:** The AI analyzes the code you type as text, but it doesn't actually execute it to check for errors or test edge cases.
*   **Human Nuance:** While the AI provides remarkably detailed analysis based on the transcript, it might not catch every subtle non-verbal cue or unspoken hesitation a human interviewer might notice. However, it offers a very strong and consistent approximation of a real evaluation process focused on what was said and coded. 

**My Next Steps:**

If I had more time, the top two things I'd add are:

1.  **Voice Interaction:** Using speech-to-text and text-to-speech would make it feel much more like a real, immersive conversation. This is my #1 priority!
2.  **Code Execution:** Letting the AI actually run the code against test cases would provide even more valuable feedback.

### Who Is This For?

Honestly, I think anyone preparing for technical interviews could find this useful:

*   **Beginners:** Can get practice explaining their thoughts and benefit from the guided hints and personalized learning plans.
*   **Experienced Devs:** Can refresh their knowledge and practice articulating complex solutions clearly.
*   **FAANG Aspirants:** Can get targeted practice for the kind of algorithmic and problem-solving questions common in those interviews.

### Final Thoughts

I'm really proud of how this project turned out. It started as a personal need – wanting better interview practice – and grew into a functional tool that combines several cool AI technologies. Building the conversational flow with LangGraph, integrating the whiteboard feature with Gemini, and getting detailed, grounded feedback feels like a significant step towards making AI a genuinely helpful partner in interview preparation.

**Want to see it in action or peek at the code?**

You can find the complete project in my Kaggle Notebook:

[**>>> Notebook <<<**](https://www.kaggle.com/code/satheeshbhukya1/ai-mock-technical-interviewer#Mock-Technical-Interviewer-with-Gemini-and-LangGraph)


Give it a try! I'd be thrilled to hear your feedback, suggestions, or ideas in the comments on Kaggle or below! What features would *you* find most helpful?
