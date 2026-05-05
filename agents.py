"""Demo agent registry and per-agent runtime configuration."""

from dataclasses import dataclass
from typing import Dict, Tuple

from bcrec_counselor_prompt import BCREC_COUNSELOR_PROMPT


SUKANYA_AGENT_PROMPT = """
# Sudipta - Sukanya Classes, Outbound Call Agent

## Who You Are
You are Sudipta, a warm 24-year-old female counselor from Sukanya Classes, a coaching institute in Durgapur/Raniganj. You are calling parents locally. You are not a salesperson or an IVR; you are having a real, neighborly conversation.

## How You Talk
- Default to natural Bengali-English mix (Bonglish), and mirror Hindi or English if the parent switches.
- Use short spoken sentences with light fillers like "aaa", "mane", "actually", "dekhen", "haa haa".
- You are a woman; use feminine grammar naturally, like "bolchhi" and "bhabchhi".
- Address adults respectfully as "Dada", "Boudi", or "Apni" depending on the situation.
- Ask one question at a time. Listen more than you talk.

## Call Flow
Start casually: "Haa, namaskar! Aaa... ami Sudipta bolchhi, Sukanya Classes theke. Apni ki ekhon kotha bolte parben ektu?"

If they can talk, ask whether there is any student at home from class 1 to 12. Never assume they have a child.

If there is a relevant student, understand class, board, subject pressure, homework pressure, and what kind of support the parent wants. Reflect their concern before mentioning Sukanya.

Only after understanding the situation, connect one relevant Sukanya point:
- Max 10 students per batch.
- Audio-visual learning instead of only books and blackboards.
- Real Physics, Chemistry, Biology labs.
- CCTV and pick-and-drop transport available.
- Branches: Phuljhore, Benachity, Raniganj.

## What You Know
- Classes: 1 to 12, CBSE and ICSE.
- Timings: 4 PM to 9 PM.
- Phuljhore: 1st Floor, Keshob Kunj Apartment, Sarat Pally, Nehru Road, Durgapur.
- Benachity: Jalkhabar Goli, Near DMC Parking, Benachity, Durgapur.
- Raniganj: Punjabi More, Near Royal Care Hospital, Raniganj.
- Contact: 8637583173 / 9002005526.
- Website: sukanyaclasses.com.
- Facebook: facebook.com/sukanyaclasses.

## Hard Rules
- Never quote fees. Say it depends on subject and batch, and the branch counselor can explain clearly.
- Never criticize current tuition, school, or teachers.
- Do not list every feature at once.
- If they are not interested, end warmly without pushing.
- If they ask for details, call `send_whatsapp_message` and say you are sending details on WhatsApp.
- When the conversation is over, say a warm goodbye and call `end_call`.
""".strip()


@dataclass(frozen=True)
class AgentConfig:
    id: str
    name: str
    description: str
    voice: str
    system_prompt: str
    first_turn_instruction: str
    whatsapp_standard_info: str
    tools: Tuple[str, ...]

    def public_dict(self) -> Dict[str, str]:
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "voice": self.voice,
        }


AGENTS: Dict[str, AgentConfig] = {
    "bcrec": AgentConfig(
        id="bcrec",
        name="BCREC Admissions",
        description="B.Tech admissions counselor for Bidhan Chandra Roy Engineering College.",
        voice="Leda",
        system_prompt=BCREC_COUNSELOR_PROMPT,
        first_turn_instruction=(
            "Greet the user naturally and briefly in Bengali. "
            "Something like: 'Namaskar, ami Sudipta bolchhi BC Roy Engineering College, Durgapur theke. Apni ki ek minute kotha bolte parben?' "
            "Then wait for their response."
        ),
        whatsapp_standard_info="""
Bidhan Chandra Roy Engineering College, Durgapur (BC Roy Engineering College / BCREC)
B.Tech Courses: Civil, CSD, CSE, CSE (AI & ML), CSE (Data Science), CSE (Cyber Security), Electrical, ECE, IT, Mechanical

Official Website: https://www.bcrec.ac.in
B.Tech Courses: https://www.bcrec.ac.in/btech-courses/kolkata-westbengal
Admission Enquiry: https://www.bcrec.ac.in/inquery
Admission Process: https://www.bcrec.ac.in/custom-page/62a71b1551f19
Phone: (0343)-2501353, 2504106
Mobile: +91-6297128554
Email: info@bcrec.ac.in
""".strip(),
        tools=("send_whatsapp_message", "search_bcrec_course_details", "end_call"),
    ),
    "sukanya": AgentConfig(
        id="sukanya",
        name="Sukanya Classes",
        description="Parent outreach counselor for Sukanya Classes coaching demos.",
        voice="Leda",
        system_prompt=SUKANYA_AGENT_PROMPT,
        first_turn_instruction=(
            "Greet the user naturally and briefly in Bengali. "
            "Something like: 'Haa, namaskar! Ami Sudipta bolchhi, Sukanya Classes theke. Apni ki ekhon kotha bolte parben ektu?' "
            "Then wait for their response."
        ),
        whatsapp_standard_info="""
Sukanya Classes
Classes: 1 to 12, CBSE and ICSE
Timings: 4 PM to 9 PM

Branches:
1. Phuljhore: 1st Floor, Keshob Kunj Apartment, Sarat Pally, Nehru Road, Durgapur
2. Benachity: Jalkhabar Goli, Near DMC Parking, Benachity, Durgapur
3. Raniganj: Punjabi More, Near Royal Care Hospital, Raniganj

Contact: 8637583173 / 9002005526
Website: sukanyaclasses.com
Facebook: facebook.com/sukanyaclasses
""".strip(),
        tools=("send_whatsapp_message", "end_call"),
    ),
}

DEFAULT_AGENT_ID = "bcrec"


def normalize_agent_id(agent_id: str | None) -> str:
    if agent_id and agent_id in AGENTS:
        return agent_id
    return DEFAULT_AGENT_ID


def get_agent_config(agent_id: str | None = None) -> AgentConfig:
    return AGENTS[normalize_agent_id(agent_id)]


def list_agents() -> list[Dict[str, str]]:
    return [agent.public_dict() for agent in AGENTS.values()]
