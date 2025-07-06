const chatBox = document.getElementById('chat-box');
const startBtn = document.getElementById('start-btn');

const recognition = new (window.SpeechRecognition || window.webkitSpeechRecognition)();
recognition.lang = 'en-US';
recognition.interimResults = false;

startBtn.onclick = () => {
    recognition.start();
    startBtn.classList.add("listening");
    startBtn.textContent = "🎙️ Listening...";
};

let isListening = false;

startBtn.onclick = () => {
    if (isListening) return;
    isListening = false;
    recognition.start();
    startBtn.classList.add("listening");
    startBtn.textContent = "🎙️ Listening...";
};

recognition.onend = () => {
    isListening = false;
    startBtn.classList.remove("listening");
    startBtn.textContent = "🎤 Ask";
};


recognition.onend = () => {
    startBtn.classList.remove("listening");
    startBtn.textContent = "🎤 Ask";
};


recognition.onresult = async (event) => {
    const userMessage = event.results[0][0].transcript;
    addMessage(userMessage, 'user');
    const response = await fetch('/ask', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: userMessage })
    });
    const data = await response.json();
    const botMessage = data.response;
    speak(botMessage);
    addMessage(botMessage, 'bot');
};

function addMessage(text, sender) {
    const div = document.createElement('div');
    div.className = `message ${sender}`;
    if (sender === 'bot') {
        let span = document.createElement('span');
        span.className = 'typing-effect';
        span.textContent = text;
        div.appendChild(span);
    } else {
        div.textContent = "👤 " + text;
    }
    chatBox.appendChild(div);
    chatBox.scrollTop = chatBox.scrollHeight;
}

function speak(text) {
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.lang = 'en-US';
    window.speechSynthesis.speak(utterance);
}
