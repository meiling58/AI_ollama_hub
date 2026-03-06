import streamlit as st
import pandas as pd
from src.engine import HubEngine
import subprocess
import re
import ollama

# 1. SETUP & HARDWARE DETECTION
st.set_page_config(page_title="Ollama Specialist Hub", layout="wide")


@st.cache_data(ttl=300)
def get_gpu_info():
    try:
        cmd = ["powershell", "Get-CimInstance Win32_VideoController | Select-Object Name, AdapterRAM"]
        output = subprocess.check_output(cmd).decode()
        for line in output.split('\n'):
            if "Radeon" in line:
                raw_bytes = re.findall(r'\d+', line)
                if raw_bytes:
                    vram_gb = round(int(raw_bytes[-1]) / (1024 ** 3), 1)
                    return {"name": "AMD Radeon™ Graphics", "vram_gb": vram_gb}
        return None
    except:
        return None


@st.cache_data(ttl=10)
def get_detailed_inventory():
    """Strictly parses Ollama list by looking for the size units specifically."""
    empty_df = pd.DataFrame(columns=["Model", "Size (GB)"])
    try:
        raw_list = subprocess.check_output(["ollama", "list"]).decode()
        lines = raw_list.strip().split('\n')[1:]

        inventory = []
        for line in lines:
            # Match the model name (start of line) and the size (number + GB/MB/KB)
            # This ignores the ID column entirely
            name_match = re.match(r"^([^\s]+)", line)
            size_match = re.search(r"(\d+\.?\d*)\s*(GB|MB|KB)", line, re.IGNORECASE)

            if name_match and size_match:
                name = name_match.group(1)
                val = float(size_match.group(1))
                unit = size_match.group(2).upper()

                if unit == "MB":
                    final_gb = val / 1024
                elif unit == "KB":
                    final_gb = val / (1024 * 1024)
                else:  # GB
                    final_gb = val

                inventory.append({"Model": name, "Size (GB)": round(final_gb, 3)})

        return pd.DataFrame(inventory)
    except:
        return empty_df


# 2. DATA LOADING
gpu = get_gpu_info()
df_inventory = get_detailed_inventory()
engine = HubEngine('data/ollama_library.json')

if not df_inventory.empty:
    installed_models = set(df_inventory["Model"].tolist())
    total_used = round(df_inventory["Size (GB)"].sum(), 2)
    # Corrected Brain Power: Total GB * 2 (approx parameters for 4-bit models)
    total_params = round(total_used * 2.0, 1)
    installed_tags = df_inventory["Model"].tolist()
else:
    installed_models, total_used, total_params, installed_tags = set(), 0.0, 0.0, []

# --- 3. DASHBOARD ---
st.title("🦙 Ollama Specialist Hub")
m1, m2, m3 = st.columns(3)
with m1:
    st.metric("📦 Disk Usage", f"{total_used} GB", delta=f"{len(installed_models)} Models")
with m2:
    st.metric("🧠 Brain Power", f"{total_params} B")
with m3:
    if gpu:
        st.metric("🎮 iGPU VRAM", f"{gpu['vram_gb']} GB")

# Health Bar
storage_target = 50.0
if total_used > storage_target:
    st.error(f"🚨 Storage Limit Warning: {total_used}GB / {storage_target}GB")
else:
    st.success(f"✅ Storage Healthy: {total_used}GB / {storage_target}GB")
st.progress(min(total_used / storage_target, 1.0))

st.divider()

# --- 4. CHAT (STAY AT TOP VERSION) ---
st.header("💬 Specialist Chat")

if installed_models:
    # We create a main frame for the chat so it doesn't "leak" to the bottom
    chat_frame = st.container(border=True)

    with chat_frame:
        c1, c2 = st.columns([4, 1])
        with c1:
            chat_model = st.selectbox("Select Model:", list(installed_models), label_visibility="collapsed")
        with c2:
            if st.button("🗑️ Reset Chat", use_container_width=True):
                st.session_state.messages = []
                st.rerun()

        # Scrollable area for messages
        chat_container = st.container(height=300)

        # The input box - by putting it inside 'with chat_frame', it stays under the selector
        prompt = st.chat_input(f"Message {chat_model}...")

    if "messages" not in st.session_state:
        st.session_state.messages = []

    # Display history
    with chat_container:
        for m in st.session_state.messages:
            with st.chat_message(m["role"]):
                st.markdown(m["content"])

    # Logic
    if prompt:
        st.session_state.messages.append({"role": "user", "content": prompt})
        with chat_container:
            st.chat_message("user").markdown(prompt)

        with chat_container:
            with st.chat_message("assistant"):
                with st.spinner("Processing..."):
                    try:
                        # Safety: 5700G memory guard
                        history = [{"role": m["role"], "content": m["content"]} for m in st.session_state.messages[-4:]]
                        response = ollama.chat(model=chat_model, messages=history)
                        answer = response['message']['content']
                        st.markdown(answer)
                        st.session_state.messages.append({"role": "assistant", "content": answer})
                    except Exception as e:
                        st.error(f"Hardware Reset Detected: {e}")
else:
    st.info("No models detected.")

st.divider()

#--- 5. LIBRARY DISCOVERY ---
st.header("🔎 Model Library Discovery")
st.sidebar.header("Filter Models")
task_filter = st.sidebar.multiselect("Capabilities", ["vision", "tools", "thinking", "embedding"])

st.sidebar.divider()
st.sidebar.header("📂 Local Storage")
if installed_tags:
    st.sidebar.pills("Installed", installed_tags, selection_mode="multi", disabled=True)
    st.sidebar.caption(f"Total Disk Usage: {total_used} GB")

results = engine.recommend()
df = pd.DataFrame(results)

if task_filter:
    def match_tasks(model_caps):
        model_caps_clean = [str(c).lower() for c in model_caps]
        return any(t.lower() in model_caps_clean for t in task_filter)
    df = df[df['capabilities'].apply(match_tasks)]

cols = st.columns(3)
for i, row in df.iterrows():
    with cols[i % 3]:
        with st.container(border=True):
            st.subheader(row['model_name'])
            version_options = [f"{v['name']} ✅" if v['name'] in installed_models else v['name'] for v in row['versions']]
            selected_display = st.selectbox("Tag", version_options, key=f"select_{i}", label_visibility="collapsed")
            selected_tag = selected_display.replace(" ✅", "")

            v_data = next(v for v in row['versions'] if v['name'] == selected_tag)
            params = engine.parse_params(v_data['size'])
            vram_req = round((params * 0.7) + 2, 1)

            if vram_req < (engine.specs['total_ram'] * 0.6): status_badge, is_too_large = "✅ Smooth", False
            elif vram_req < engine.specs['total_ram']: status_badge, is_too_large = "⚠️ Heavy", False
            else: status_badge, is_too_large = "❌ Too Large", True

            st.caption(f"Status: {status_badge} | VRAM Req: {vram_req}GB")
            st.write(row['summary'][:100] + '...')

            if selected_tag in installed_models:
                if st.button(f"🗑️ Remove", key=f"remove_{i}"):
                    subprocess.run(["ollama", "rm", selected_tag])
                    st.cache_data.clear()
                    st.rerun()
            else:
                if is_too_large:
                    st.button("🚀 Install", key=f"inst_{i}", disabled=True)
                    st.error("Insufficient RAM")
                else:
                    if st.button(f"🚀 Install", key=f"inst_{i}"):
                        with st.spinner(f"Pulling {selected_tag}..."):
                            subprocess.run(["ollama", "pull", selected_tag])
                            st.cache_data.clear()
                            st.rerun()
