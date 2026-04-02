import sys
import uuid
import logging
from pathlib import Path

# Add repo root for shared imports
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from dotenv import load_dotenv
load_dotenv()

# Setup logging to console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

import streamlit as st
from langchain_core.messages import HumanMessage

from agents.v2.graph import compile_graph

st.set_page_config(
    page_title="WiFi Troubleshooting Assistant V2",
    page_icon="📶",
    layout="centered",
)

st.title("WiFi Troubleshooting Assistant V2")

TERMINAL_NODES = ("graceful_exit", "close_success", "apologize_and_exit", "unsupported_model_exit")

# --- Mode Selection (before graph starts) ---
if "conversation_mode" not in st.session_state:
    st.subheader("How would you like to troubleshoot?")
    mode = st.radio(
        "Select conversation mode:",
        options=["self_serve", "agent_assisted"],
        format_func=lambda x: "I'll troubleshoot on my own" if x == "self_serve" else "An agent will help me",
        horizontal=True,
    )
    if st.button("Start"):
        st.session_state.conversation_mode = mode
        st.rerun()
    st.stop()

# --- Session State Init ---
if "thread_id" not in st.session_state:
    st.session_state.thread_id = str(uuid.uuid4())
if "messages" not in st.session_state:
    st.session_state.messages = []
if "conversation_ended" not in st.session_state:
    st.session_state.conversation_ended = False
if "graph" not in st.session_state:
    st.session_state.graph = compile_graph()
if "welcome_sent" not in st.session_state:
    st.session_state.welcome_sent = False

graph = st.session_state.graph
config = {
    "configurable": {"thread_id": st.session_state.thread_id},
    "run_name": "wifi-troubleshoot-v2",
}

# --- Initial welcome invocation (no user input needed) ---
if not st.session_state.welcome_sent:
    logger.info(f"Triggering welcome flow for mode: {st.session_state.conversation_mode}")
    try:
        # Invoke graph with mode but no user message to trigger welcome node
        graph.invoke(
            {"messages": [], "conversation_mode": st.session_state.conversation_mode},
            config=config,
        )
        state = graph.get_state(config)
        state_messages = state.values.get("messages", [])
        logger.info(f"Welcome invocation returned {len(state_messages)} messages")

        # Extract welcome message
        for msg in reversed(state_messages):
            if hasattr(msg, 'type') and msg.type == "ai":
                welcome_text = msg.content
                st.session_state.messages.append({"role": "assistant", "content": welcome_text})
                logger.info(f"Welcome message: {welcome_text[:80]}")
                break

        st.session_state.welcome_sent = True
    except Exception as e:
        logger.error(f"Welcome invocation error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        st.error(f"Error starting conversation: {str(e)}")

# --- Render chat history ---
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# --- Chat input loop ---
if not st.session_state.conversation_ended:
    if prompt := st.chat_input("Type your message..."):
        logger.info(f"User input received: {prompt[:80]}")

        if not prompt.strip():
            st.warning("Please enter a message.")
            st.stop()

        # Add user message to display
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)

        # Invoke graph with user message
        with st.chat_message("assistant"):
            with st.spinner("Thinking..."):
                try:
                    logger.info(f"Invoking graph (thread: {st.session_state.thread_id})")

                    # Invoke graph with user message
                    graph.invoke(
                        {"messages": [HumanMessage(content=prompt)]},
                        config=config,
                    )

                    # After invoke, get current state
                    state = graph.get_state(config)
                    logger.info(f"State after invoke — next: {state.next}")

                    # Extract the last AI message from the state values
                    response = None
                    state_messages = state.values.get("messages", [])
                    logger.info(f"Total messages in state: {len(state_messages)}")

                    # Walk backwards to find the last AI message
                    for msg in reversed(state_messages):
                        if hasattr(msg, 'type') and msg.type == "ai":
                            if hasattr(msg, 'content') and isinstance(msg.content, str) and msg.content.strip():
                                response = msg.content
                                break

                    if response is None:
                        logger.warning("No AI response found in state")
                        response = "I'm sorry, I encountered an issue processing your message. Please try again."

                    logger.info(f"Response: {response[:100]}")
                    st.markdown(response)

                    # Check if conversation ended (terminal node was reached)
                    last_executed_node = state.values.get("last_executed_node", "")
                    logger.info(f"Current node: {last_executed_node}")

                    if last_executed_node in TERMINAL_NODES:
                        logger.info("Conversation ended")
                        st.session_state.conversation_ended = True

                except Exception as e:
                    import traceback
                    logger.error(f"Exception: {str(e)}")
                    logger.error(traceback.format_exc())
                    response = f"Error: {str(e)}"
                    st.error(response)
                    with st.expander("Debug Info"):
                        st.code(traceback.format_exc())

        st.session_state.messages.append({"role": "assistant", "content": response})
        st.rerun()
else:
    st.info("Conversation ended. Refresh the page to start a new session.")
    if st.button("Start New Conversation"):
        st.session_state.clear()
        st.rerun()
