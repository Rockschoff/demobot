import streamlit as st
from openai import OpenAI
from tavily import TavilyClient
import time
import json
import requests

client = OpenAI(api_key=st.secrets["OPENAI_API_KEY"])

tavily_client = TavilyClient(api_key=st.secrets["TAVILY_API_KEY"])

def search_FDA_guidance_docs(search_terms : str)->str:
    print("Searching FDA", search_terms)
    response = tavily_client.search(search_terms, include_domains=["fda.gov", "accessdata.fda.gov"])
    print(response["results"])
    return str(response)

def search_cfr_title_21(search_terms: str) -> str:
    print("Searching CFR", search_terms)
    try:
        # Encode the search terms for URL
        encoded_search_terms = requests.utils.quote(search_terms)
        
        # Construct the URL
        url = f"https://www.ecfr.gov/api/search/v1/results?query={encoded_search_terms}&per_page=25&page=1&order=relevance&paginate_by=results"
        
        # Define headers for the GET request
        headers = {
            'Accept': 'application/json'
        }
        
        # Send GET request to the URL
        response = requests.get(url, headers=headers)
        
        # Raise an exception if the status code indicates an error
        response.raise_for_status()
        
        # Parse JSON response
        data = response.json()
        
        # Extract relevant fields from the response
        hierarchy_text = [f"{ele['full_text_excerpt']} {json.dumps(ele['hierarchy_headings'])}" for ele in data['results']]
        
        # Debug: Print the length of each hierarchy text for inspection
        print([len(ele) for ele in hierarchy_text])
        
        # Join the hierarchy text with newline and return it
        return "\n".join(hierarchy_text)
    
    except requests.exceptions.RequestException as e:
        # Handle any request-related errors
        print('There was an error with the fetch operation:', e)
        return "Error getting response from CFR"


def create_thread():
    empty_thread = client.beta.threads.create()
    print(empty_thread)
    return empty_thread.id

def load_thread():
    thread_messages = client.beta.threads.messages.list(st.session_state.thread_id)
    
    return [{"role" : d.role , "content":d.content[0].text.value} for d in thread_messages.data]

def get_response():
    client.beta.threads.messages.create(
        st.session_state.thread_id,
        role=st.session_state.messages[-1]["role"],
        content=st.session_state.messages[-1]["content"],
    )
    
    run = client.beta.threads.runs.create(
        thread_id=st.session_state.thread_id,
        assistant_id=st.secrets["OPENAI_ASSISTANT_ID2"],
        tool_choice={"type": "function", "function": {"name": "Search_FDA_Guidance_Docs"}}
    )
    
    def wait_on_run(run):
        count = 0
        while run.status in ["queued", "in_progress", "requires_action"]:
            count += 1
            print("Waiting", count)
            
            if run.status == "requires_action":
                tool_outputs = []
                tool_calls = run.required_action.submit_tool_outputs.tool_calls
                
                for tool_call in tool_calls:
                    if tool_call.function.name == "Search_CFR_Title_21":
                        print(tool_call.function.arguments)
                        response = search_cfr_title_21(json.loads(tool_call.function.arguments)["search_terms"])
                    elif tool_call.function.name == "Search_FDA_Guidance_Docs":
                        print(tool_call.function.arguments)
                        response = search_FDA_guidance_docs(json.loads(tool_call.function.arguments)["search_terms"])
                    
                    tool_outputs.append({"tool_call_id": tool_call.id, "output": response})
                
                run = client.beta.threads.runs.submit_tool_outputs(
                    thread_id=st.session_state.thread_id,
                    run_id=run.id,
                    tool_outputs=tool_outputs
                )
            
            run = client.beta.threads.runs.retrieve(
                thread_id=run.thread_id,
                run_id=run.id,
            )
            time.sleep(0.5)
        
        return run
    
    run = wait_on_run(run)
    
    messages = client.beta.threads.messages.list(thread_id=run.thread_id)
    ans = messages.data[0].content[0].text.value
    
    return ans

st.title("Echo Bot")



if "thread_id" not in st.session_state:
    st.session_state.thread_id = create_thread()

# Initialize chat history
if "messages" not in st.session_state:
    st.session_state.messages = load_thread()



# Display chat messages from history on app rerun
for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])

# React to user input
if prompt := st.chat_input("What is up?"):
    # Display user message in chat message container
    st.chat_message("user").markdown(prompt)
    # Add user message to chat history
    st.session_state.messages.append({"role": "user", "content": prompt})
    

    response = get_response()
    # Display assistant response in chat message container
    with st.chat_message("assistant"):
        st.markdown(response)
    # Add assistant response to chat history
    st.session_state.messages.append({"role": "assistant", "content": response})