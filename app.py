import streamlit as st
import replicate
import os
import pytesseract
from PIL import Image
import pdfplumber
from transformers import AutoTokenizer, pipeline

icons = {"assistant": "🤖", "user": "human"}

# App title
st.set_page_config(page_title="Food Inspector")

# Replicate Credentials
with st.sidebar:
    if 'REPLICATE_API_TOKEN' in st.secrets:
        replicate_api = st.secrets['REPLICATE_API_TOKEN']
    else:
        replicate_api = st.text_input('Enter Replicate API token:', type='password')
        if not (replicate_api.startswith('r8_') and len(replicate_api)==40):
            st.warning('Please enter your Replicate API token.', icon='⚠️')
            st.markdown("**Don't have an API token?** Head over to [Replicate](https://replicate.com) to sign up for one.")

    os.environ['REPLICATE_API_TOKEN'] = replicate_api
    st.subheader("Adjust model parameters")
    temperature = st.slider('temperature', min_value=0.01, max_value=5.0, value=0.3, step=0.01)
    top_p = st.slider('top_p', min_value=0.01, max_value=1.0, value=0.9, step=0.01)
    
    st.subheader("Upload PDF or Image")
    uploaded_file = st.file_uploader("", type=["pdf", "png", "jpg", "jpeg"])

# Store LLM-generated responses
if "messages" not in st.session_state.keys():
    st.session_state.messages = [{"role": "assistant", "content": "As a food inspector, I will read and understand all food contents of packaging, identifying if any are hazardous to health or banned in any country. Ask me anything."}]

# Display or clear chat messages
for message in st.session_state.messages:
    with st.chat_message(message["role"], avatar=icons[message["role"]]):
        st.write(message["content"])

def clear_chat_history():
    st.session_state.messages = [{"role": "assistant", "content": "As a food inspector, I will read and understand all food contents of packaging, identifying if any are hazardous to health or banned in any country. Ask me anything."}]

st.button('Clear chat history', on_click=clear_chat_history, help="Clears the chat history")

@st.cache_resource(show_spinner=False)
def get_tokenizer():
    return AutoTokenizer.from_pretrained("huggyllama/llama-7b")

@st.cache_resource(show_spinner=False)
def get_classifier():
    return pipeline("sentiment-analysis")

def get_num_tokens(prompt):
    tokenizer = get_tokenizer()
    tokens = tokenizer.tokenize(prompt)
    return len(tokens)

def extract_text_from_pdf(file):
    text = ""
    with pdfplumber.open(file) as pdf:
        for page in pdf.pages:
            text += page.extract_text()
    return text

def extract_text_from_image(file):
    image = Image.open(file)
    text = pytesseract.image_to_string(image)
    return text

def classify_food_content(text):
    classifier = get_classifier()
    result = classifier(text)
    return result

# Function for generating Snowflake Arctic response
def generate_arctic_response():
    prompt = []
    for dict_message in st.session_state.messages:
        if dict_message["role"] == "user":
            prompt.append("user\n" + dict_message["content"] + "")
        else:
            prompt.append("assistant\n" + dict_message["content"] + "")
    
    prompt.append("assistant")
    prompt.append("")
    prompt_str = "\n".join(prompt)
    
    if get_num_tokens(prompt_str) >= 3072:
        st.error("Conversation length too long. Please keep it under 3072 tokens.")
        st.button('Clear chat history', on_click=clear_chat_history, key="clear_chat_history")
        st.stop()

    for event in replicate.stream("snowflake/snowflake-arctic-instruct",
                           input={"prompt": prompt_str,
                                  "prompt_template": r"{prompt}",
                                  "temperature": temperature,
                                  "top_p": top_p,
                                  }):
        yield str(event)

# User-provided prompt
if prompt := st.chat_input(disabled=not replicate_api, placeholder="Type here to ask about food contents"):
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.form(key="send_message_form"):
        col1, col2 = st.columns([8, 1])
        with col1:
            st.write(prompt)
        with col2:
            st.form_submit_button(label="Send", help="Send your message")

# Generate a new response if last message is not from assistant
if st.session_state.messages[-1]["role"] != "assistant":
    with st.chat_message("assistant", avatar="🤖"):
        response = generate_arctic_response()
        full_response = st.write_stream(response)
    message = {"role": "assistant", "content": full_response}
    st.session_state.messages.append(message)

# File upload
if uploaded_file is not None:
    if uploaded_file.type == "application/pdf":
        text = extract_text_from_pdf(uploaded_file)
    else:
        text = extract_text_from_image(uploaded_file)
    
    st.subheader("Extracted Text")
    st.write(text)
    
    st.subheader("Food Content Analysis")
    analysis = classify_food_content(text)
    st.write(analysis)
