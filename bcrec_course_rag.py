"""Hybrid retrieval and lightweight reranking for BCREC B.Tech course context.

This module keeps course documents local and dependency-light. It implements:
- contextual chunks: every chunk carries course, section, source, and a compact context prefix
- hybrid retrieval: lexical BM25-style scoring + semantic-ish TF-IDF cosine scoring
- reranking: query/course/section/exact-phrase boosts on top of hybrid candidates
"""

from __future__ import annotations

import math
import re
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import Iterable


@dataclass(frozen=True)
class CourseDocument:
    slug: str
    course: str
    aliases: tuple[str, ...]
    url: str
    summary: str
    details: dict[str, str]


@dataclass(frozen=True)
class ContextualChunk:
    chunk_id: str
    course_slug: str
    course: str
    section: str
    source_url: str
    context: str
    text: str

    @property
    def contextual_text(self) -> str:
        return f"{self.context}\n{self.text}"


BCREC_COURSE_DOCUMENTS: tuple[CourseDocument, ...] = (
    CourseDocument(
        slug="civil-engineering",
        course="Civil Engineering",
        aliases=("civil", "ce", "construction", "infrastructure"),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-civil-engineering",
        summary=(
            "B.Tech Civil Engineering started in 2010 with current intake 60. The department also lists a B.Tech "
            "Civil Engineering programme for Working Professionals started in 2024 with intake 60. It focuses on "
            "construction, infrastructure, structural/geotechnical/transportation/environmental engineering, practical labs, "
            "industry internships and core civil career pathways."
        ),
        details={
            "intake_and_programs": "Year of establishment 2010. B.Tech in Civil Engineering is a 4-year programme, year of commencement 2010, current intake 60. B.Tech in Civil Engineering for Working Professionals commenced in 2024 with current intake 60.",
            "overview": "The department teaches building, construction and major civil engineering areas. It has laboratories for Solid Mechanics, Concrete Technology, Soil Mechanics, Highway and Transportation Engineering, Fluid Mechanics, Surveying, Water Resources Engineering, Environmental Engineering and Project work, plus computational facilities.",
            "industry_and_careers": "The department mentions MoU activity with NHAI where twenty students get two-month paid internships, consultancy quality control work for local construction companies, and a Centre of Excellence by UltraTech. Career pathways include Assistant/Sub-Assistant Engineer, Site Engineer, Design Engineer, Quality Control Engineer, Estimation and Valuation Engineer, BIM/GIS specialist, Infrastructure Auditor and Safety Manager.",
            "placements_and_recruiters": "The public page mentions recruiters such as Shapoorji and Pallonji, MEIL, UltraTech Cement, Sobha Developers, Skipper, SPL Infrastructure, Shree Prefab and Sannverse Railtech. It says many eligible students get placed through campus drives and students also pursue M.Tech, MBA, PhD and MS at reputed institutes in India and abroad.",
            "research_and_labs": "Research areas include Structural Engineering, Structural Health Monitoring, Concrete Technology and Sustainable Development, Geotechnical Engineering, Transportation and Traffic Engineering, and Environmental Engineering.",
            "hod": "HoD listed: Dr. Sanjay Sengupta. Contact email: sanjay.sengupta@bcrec.ac.in. Contact numbers listed: 9836303034 / 9064179712.",
        },
    ),
    CourseDocument(
        slug="computer-science-and-design",
        course="Computer Science and Design",
        aliases=(
            "csd",
            "computer science design",
            "design",
            "ui ux",
            "ar vr",
            "game design",
        ),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-computer-science-and-design",
        summary=(
            "B.Tech Computer Science and Design started in 2021 with current intake 60. It combines computing with "
            "interactive design, digital media, UI/UX, AR/VR, animation, game development, machine learning, data analytics, "
            "web development, IoT/robotics and CAD/3D printing."
        ),
        details={
            "intake_and_programs": "Year of establishment 2021. B.Tech in Computer Science and Design is a 4-year programme, year of commencement 2021, current intake 60.",
            "overview": "The programme develops graduates who are well versed with computing approaches, tools and technologies, and also experienced with design approaches, new media technologies and interactive design methods.",
            "career_scope": "The programme prepares students for IT and digital media industries including machine learning, robotics, IoT, animation, game development, virtual/augmented reality, web applications, blockchain and cyber security. It also supports higher studies in CS/IT or Design.",
            "labs": "Labs include Programming/Algorithm/Data Structure, Python/Data Analytics/Visualization/Machine Learning, DBMS/Operating Systems, Robotics/IoT, Computer Organization and Digital Lab, AR/VR Lab, Project Lab, Graphics Design/Animation/Game Development Lab, and CAD/3D Printing Lab.",
            "focus": "Focus areas include outcome-based education, fundamental/core concepts, practical applications, IT skill development, personality and communication skills, values and ethics, industry placements, programming competitions, national/international contests and student counselling.",
            "hod": "HoD listed: Dr. Poulomi Mukherjee Tewari. Contact email: poulami.mukherjee@bcrec.ac.in.",
        },
    ),
    CourseDocument(
        slug="computer-science-and-engineering",
        course="Computer Science and Engineering",
        aliases=("cse", "computer science", "coding", "software", "programming"),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-computer-science-and-engineering",
        summary=(
            "B.Tech CSE started in 2000 with current intake 180; M.Tech CSE intake 18. The department is NBA accredited "
            "and focuses on core computing, labs, research, industry interaction and strong software placement pathways."
        ),
        details={
            "intake_and_programs": "Year of establishment 2000. B.Tech in Computer Science and Engineering is a 4-year programme with current intake 180. M.Tech in Computer Science and Engineering is a 2-year programme with current intake 18.",
            "accreditation": "The department page states NBA accreditation for 2009-2012, 2016-2019 and 2020-2023.",
            "overview": "The department follows Outcome-Based Education with interactive teaching-learning, modern labs, departmental library, seminar hall and digital classroom. Faculty are described as qualified and research active.",
            "placements": "The department page mentions students placed in Capgemini, TCS, Infosys, IBM, Tech Mahindra, Wipro, Accenture and other organizations. Students also pursue higher studies through GATE and GRE.",
            "labs": "Labs include Basic Programming Language and Data Structure, Computer Graphics, Operating Systems, Intra Networking, Software Design, Turing Fundamental Computing, Advanced Programming, Database Management and Computer Organization.",
            "collaborations": "Collaborations shown on the page include AEM, AWS, Infosys and Red Hat logos.",
            "hod": "HoD listed: Dr. Raj Kumar Samanta. Contact email: rajkumar.samanta@bcrec.ac.in. Contact number listed: 9333336958.",
        },
    ),
    CourseDocument(
        slug="cse-ai-ml",
        course="Computer Science and Engineering (Artificial Intelligence and Machine Learning)",
        aliases=(
            "aiml",
            "ai ml",
            "artificial intelligence",
            "machine learning",
            "deep learning",
            "nlp",
            "computer vision",
        ),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-computer-science-and-engineering-artificial-intelligence-and-machine-learning",
        summary=(
            "B.Tech CSE (AI & ML) started in 2021 with intake 60. It builds a computer science base with AI, ML, "
            "deep learning, NLP, computer vision, data engineering, robotics and responsible AI."
        ),
        details={
            "intake_and_programs": "Year of establishment 2021. B.Tech in CSE (AI & ML) is a 4-year programme, current intake 60.",
            "overview": "The course aims to develop a strong engineering foundation through statistical and probabilistic models, logic, knowledge engineering and machine learning. Students explore NLP, deep learning, robotics and computer vision.",
            "career_pathways": "Career pathways listed include AI Research Scientist, Machine Learning Engineer, Data Scientist, NLP Specialist, Computer Vision Engineer, AI Architect, Cognitive Systems Developer, Big Data Engineer, AI Ethicist and compliance-related roles.",
            "labs": "Labs include Artificial Intelligence Lab, Machine Learning Lab, Data Handling and Data Visualization Lab, Soft Computing Lab, Programming Language and Data Structure Lab, Object Oriented Programming Lab, Web Development Lab and Networking Lab.",
            "research": "Research strength areas include Artificial Intelligence and Machine Learning, Computer Vision and Medical Imaging, Vision-Language Models, Explainable AI, Gesture and Sign Language Recognition, Industrial AI and Predictive Analytics, and Embedded AI Systems.",
            "hod": "HoD listed: Dr. Gour Sundar Mitra Thakur. Contact email: gour.mitrathakur@bcrec.ac.in.",
        },
    ),
    CourseDocument(
        slug="cse-data-science",
        course="Computer Science and Engineering (Data Science)",
        aliases=("data science", "ds", "analytics", "data analytics", "data scientist"),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-computer-science-and-engineering-data-science",
        summary=(
            "B.Tech CSE (Data Science) started in 2022 with intake 60. It combines computer science, computational "
            "mathematics, statistics and management for analytics, visualization, predictive modeling and data-driven decisions."
        ),
        details={
            "intake_and_programs": "Year of establishment 2022. B.Tech in CSE (Data Science) is a 4-year programme with current intake 60.",
            "overview": "The programme focuses on interpreting data correctly, generating ideas from data, and developing foundations in Computer Science, Computational Mathematics, Statistics and Management. It includes data analytics, visualization, predictive modeling, knowledge representation, machine learning and deep learning.",
            "career_scope": "In-demand roles listed include Data Analyst, Data Engineer, Database Administrator, Machine Learning Engineer, Data Scientist, Data Architect, Statistician, Business Analyst, and Data and Analytics Manager.",
            "labs": "Labs include Artificial Intelligence Lab, Machine Learning Lab, Soft Computing Lab, Programming Language and Data Structure Lab, Networking Lab, Computer Architecture Lab, Data Science Lab, Big Data and Machine Learning Lab, Data Analytics and Visualization Lab and Project Lab.",
            "research": "Research areas listed include Quantum Computing, Reversible Logic Synthesis, Machine Learning, Uncertainty Theory, Evolutionary Algorithms, IoT and Citation Network.",
            "hod": "HoD listed: Dr. Chandan Bandyopadhyay. Contact email: chandan.bandyopadhyay@bcrec.ac.in.",
        },
    ),
    CourseDocument(
        slug="cse-cyber-security",
        course="Computer Science and Engineering (Cyber Security)",
        aliases=(
            "cyber security",
            "cybersecurity",
            "ethical hacking",
            "network security",
            "digital forensics",
        ),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-computer-science-and-engineering-cyber-security",
        summary=(
            "B.Tech CSE (Cyber Security) started in 2024 with intake 60. It blends core computer science with "
            "cryptography, ethical hacking, network/cloud security, system security, digital forensics and cyber threat analysis."
        ),
        details={
            "intake_and_programs": "Year of establishment 2024. B.Tech in CSE (Cyber Security) is a 4-year programme, current intake 60.",
            "overview": "The programme addresses demand for security professionals in data security and network/cloud security. It covers core CS subjects as well as cybersecurity-specific courses, including secure computers, attack detection and analysis, response, policies, procedures and standards.",
            "career_pathways": "Career pathways listed include Cyber Security Analyst, Ethical Hacker/Penetration Tester, Security Software Developer, Network Security Engineer, Cloud Security Specialist, Digital Forensics Expert, Security Analyst in Data Science and AI, Healthcare Data Security Specialist, Researcher/Academician, and certification-led industry roles such as CEH, CISSP and CompTIA Security+.",
            "labs": "Labs include Data Structure and Algorithms, Analog and Digital Electronics, Computer Organization, IT Workshop, Data Communication and Networks, Design and Analysis of Algorithm, System Security, Operating System, OOP, Network Security, DBMS and Project Lab. The page also describes a High-Performance Cyber Security Lab for intrusion detection, anomaly detection, DDoS simulation, IoT security, ML/DL model security and log analysis.",
            "research": "Research areas include Cyber Security and Secure Computing, Blockchain Security, Digital Forensics, AI-Driven Cyber Threat Intelligence, IoT and Smart Intelligent Systems, Biomedical Signal Processing, Explainable AI, Healthcare Data Analytics, Generative AI and Agentic Systems.",
            "hod": "HoD listed: Dr. Gour Sundar Mitra Thakur. Contact email: gour.mitrathakur@bcrec.ac.in.",
        },
    ),
    CourseDocument(
        slug="electrical-engineering",
        course="Electrical Engineering",
        aliases=(
            "ee",
            "electrical",
            "power system",
            "renewable",
            "ev",
            "electric vehicles",
            "smart grid",
        ),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-electrical-engineering",
        summary=(
            "B.Tech Electrical Engineering started in 2000 with current intake 120, reducing to 60 from AY 2026-27. "
            "M.Tech Power System Engineering intake 18. NBA accredited till June 2028. Focuses on power systems, "
            "electrical machines, control, power electronics, renewable energy, EVs, smart grids and automation."
        ),
        details={
            "intake_and_programs": "Year of establishment 2000. B.Tech in Electrical Engineering started in 2000 with current intake 120, noted as 60 from AY 2026-27. M.Tech in Power System Engineering started in 2007 with intake 18.",
            "accreditation": "The page states NBA Accredited till June 2028 and mentions NBA accreditation in 2008, 2022 and 2025.",
            "overview": "Research domains include renewable energy, smart grids, non-linear control and optimization, reinforcement learning, digital signal processing, analog VLSI, IoT, blockchain and biomedical instrumentation. The department mentions external consultancy projects and international collaborations.",
            "labs": "Labs include Basic Electrical Engineering, Network, Electrical and Electronic Measurement, Digital Electronics, Electrical Machine, Power System, Control Systems, Power Electronics, Microprocessor and Microcontroller, Electrical Drives, Simulation Labs I/II/III and Tesla Research Lab.",
            "placements": "EE placement details shown: highest package 7.5 LPA and average 3.94 LPA in 2023; highest 5.2 LPA and average 2.69 LPA in 2024; highest 6.0 LPA and average 3.80 LPA in 2025.",
            "research": "Research areas listed include Renewable Energy, Electric Vehicles, Control Systems, Biomedical Signal Processing, Power Systems, Analog VLSI Circuits, Fractional-order Circuits and Systems, IoT and Blockchain Technology.",
            "hod": "HoD listed: Dr. Shibendu Mahata. Contact email: shibendu.mahata@bcrec.ac.in. Contact number listed: 9832724052.",
        },
    ),
    CourseDocument(
        slug="electronics-and-communication-engineering",
        course="Electronics and Communication Engineering",
        aliases=(
            "ece",
            "electronics",
            "communication",
            "vlsi",
            "embedded",
            "telecom",
            "antenna",
        ),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-electronics-and-communication-engineering",
        summary=(
            "B.Tech ECE started in 2000 with intake 120; M.Tech intake 18. NBA accredited/re-accredited. Focuses on "
            "electronics, communication, VLSI, DSP, microwave, antenna, wireless/mobile communication, embedded systems and project-based learning."
        ),
        details={
            "intake_and_programs": "Year of establishment 2000. B.Tech in Electronics and Communication Engineering is a 4-year programme with current intake 120. M.Tech in Electronics and Engineering is listed with current intake 18.",
            "accreditation": "The page states NBA Accredited and re-accredited for Academic Year 2023-24 to 2025-26.",
            "overview": "The department emphasizes fundamentals of Electronics and Communication Engineering, small-group laboratory experiments, industrial-type final-year projects, group discussion and seminars. It also mentions advanced communication and VLSI labs, FPGA boards and simulation tools such as MATLAB, Simulink, Spice, Mentor Graphics, Xilinx and Vivado.",
            "labs": "Labs include Basic Electronics, Digital System Design, Electromagnetic Wave, Reconfigurable VLSI Simulation, Digital Signal Processing, Electronic Devices, Analog and Digital Electronics, Analog Communication, Digital Communication, Advanced Communication, Microwave Engineering, Computer Network, Electronic Design, Mini Project/Design Workshop, Research Lab, Texas Instruments Innovation Lab, VLSI Center for Excellence, Wireless and Mobile Communication, and Antenna and Radiating Systems.",
            "research": "The public page shows publications in antennas, microwave imaging, GNSS positioning, MIMO antennas, CMOS circuits, VLSI, image encryption, power distribution fault detection and nanomaterial design.",
            "hod": "HoD listed: Dr. Mrinmoy Chakraborty.",
        },
    ),
    CourseDocument(
        slug="information-technology",
        course="Information Technology",
        aliases=(
            "it",
            "information technology",
            "cloud",
            "devops",
            "software engineering",
        ),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-information-technology",
        summary=(
            "B.Tech Information Technology started in 2000 with intake 60. NBA accredited. Focuses on software, AI/ML, "
            "data science, IoT, cloud computing, cyber security, software engineering and industry-ready IT careers."
        ),
        details={
            "intake_and_programs": "Year of establishment 2000. B.Tech in Information Technology is a 4-year programme with current intake 60.",
            "accreditation": "The department page states the B.Tech IT program is NBA-accredited.",
            "overview": "The department emphasizes continuous feedback, outcome-based education, project-based learning and graduate attribute mentoring. Key focus areas include AI & ML, Data Science, IoT, Cloud Computing, Cyber Security and Software Engineering.",
            "career_scope": "The department states a near 100% placement rate within one year of graduation. Industry roles listed include Software Developer, Data Scientist, AI/ML Engineer, Cybersecurity Analyst, Cloud Architect, DevOps Engineer and Business Intelligence Analyst. Higher studies options include M.Tech, MS, MBA and Ph.D.",
            "labs": "Labs include Programming Languages/OOP/Computational Lab, Algorithm/Data Structure/DBMS/Operating System Lab, Networking/Web Technology/E-Commerce/Multimedia Lab, Computer Organisation and Architecture Lab, and Project Lab for innovation and entrepreneurship.",
            "research": "Research areas include AI/ML including Explainable AI, Quantum Machine Learning, IoT and Smart Systems, Computer Networks, Ad-hoc Networks, Cyber-Physical Systems, Renewable Energy Informatics, Financial Data Analytics, Optimization Algorithms and Edge Computing.",
            "hod": "HoD listed: Dr. Dinesh Kumar Pradhan. Contact email: dinesh.pradhan@bcrec.ac.in. Contact number listed: 9433303419.",
        },
    ),
    CourseDocument(
        slug="mechanical-engineering",
        course="Mechanical Engineering",
        aliases=(
            "me",
            "mechanical",
            "machines",
            "manufacturing",
            "cad",
            "cam",
            "robotics",
            "automobile",
        ),
        url="https://www.bcrec.ac.in/depertment-details/b-tech-mechanical-engineering",
        summary=(
            "B.Tech Mechanical Engineering started in 2003 with intake 60; M.Tech intake 18. NBA accredited up to June 2028. "
            "Focuses on CAD/CAM, robotics, mechatronics, manufacturing, thermal systems, design, automotive, energy and core industry careers."
        ),
        details={
            "intake_and_programs": "Year of establishment 2000 is shown on the page header, while the department description states Mechanical Engineering was established in 2003. B.Tech Mechanical Engineering commenced in 2003 with current intake 60. M.Tech Mechanical Engineering commenced in 2012 with current intake 18.",
            "accreditation": "The page states NBA Accreditation up to June 2028.",
            "overview": "The department offers B.Tech and M.Tech, with specialized labs such as CAD-CAM and Robotics, Mechatronics and Modern Control, plus conventional labs such as Mechanical Workshops, Thermal Lab and Dynamics of Machines. Students use software like AutoCAD, Creo and ANSYS.",
            "career_scope": "Career options include Mechanical Engineer, Aerospace Engineer, Automotive Engineer, Maintenance Engineer, Hydraulic Engineer, Design Engineer, Quality Engineer, Service Engineer, Assistant Engineer, GET, MT and Scientist roles. The page also mentions IT roles such as Software Developer, System Designer, System Analyst, Networking Engineer and Database Administrator, plus higher studies and entrepreneurship.",
            "labs": "Labs include Engineering Graphics, Fluid Mechanics and Fluid Machinery, Thermal Engineering, Applied Thermodynamics and Heat Transfer, Internal Combustion Engine, Dynamics of Machines, Measurements and Instrumentation, Machine Drawing and Design Practice, Advanced Manufacturing CAD/CAM and Robotics, Applied Mechanics, Manufacturing Process, Material Testing, Mechatronics and Modern Control, and Project Lab.",
            "research": "Research thrust areas include Robotics and Autonomous Systems, Advanced Manufacturing and Industry 4.0, Computational Mechanics and Simulation, Energy Systems and Design Engineering.",
            "hod": "HoD listed: Dr. Chandan Chattoraj. Contact email: chandan.chattoraj@bcrec.ac.in. Contact number listed: 9531591525.",
        },
    ),
)


TOKEN_RE = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> list[str]:
    return TOKEN_RE.findall(text.lower())


def _phrases(text: str) -> list[str]:
    words = _tokens(text)
    return [" ".join(words[i : i + 2]) for i in range(len(words) - 1)]


def build_contextual_chunks(
    documents: Iterable[CourseDocument] = BCREC_COURSE_DOCUMENTS,
) -> list[ContextualChunk]:
    chunks: list[ContextualChunk] = []
    for doc in documents:
        base_context = (
            f"This chunk is from the official BCREC department page for {doc.course}. "
            f"Course aliases: {', '.join(doc.aliases)}. "
            f"Use it for B.Tech admissions counseling and stream-specific questions. "
            f"Overall course summary: {doc.summary}"
        )
        chunks.append(
            ContextualChunk(
                chunk_id=f"{doc.slug}:summary",
                course_slug=doc.slug,
                course=doc.course,
                section="summary",
                source_url=doc.url,
                context=base_context,
                text=doc.summary,
            )
        )
        for section, text in doc.details.items():
            section_context = f"{base_context} Section: {section.replace('_', ' ')}."
            chunks.append(
                ContextualChunk(
                    chunk_id=f"{doc.slug}:{section}",
                    course_slug=doc.slug,
                    course=doc.course,
                    section=section,
                    source_url=doc.url,
                    context=section_context,
                    text=text,
                )
            )
    return chunks


class BCRECCourseRetriever:
    def __init__(self, chunks: Iterable[ContextualChunk] | None = None):
        self.chunks = list(chunks or build_contextual_chunks())
        self.chunk_tokens = [_tokens(chunk.contextual_text) for chunk in self.chunks]
        self.term_freqs = [Counter(tokens) for tokens in self.chunk_tokens]
        self.doc_freq: Counter[str] = Counter()
        for tokens in self.chunk_tokens:
            self.doc_freq.update(set(tokens))
        self.avg_doc_len = sum(len(tokens) for tokens in self.chunk_tokens) / max(
            len(self.chunk_tokens), 1
        )
        self.idf = {
            term: math.log(1 + (len(self.chunks) - df + 0.5) / (df + 0.5))
            for term, df in self.doc_freq.items()
        }
        self.course_alias_map = self._build_course_alias_map()

    def _build_course_alias_map(self) -> dict[str, str]:
        alias_map: dict[str, str] = {}
        for doc in BCREC_COURSE_DOCUMENTS:
            alias_map[doc.slug.replace("-", " ")] = doc.slug
            alias_map[doc.course.lower()] = doc.slug
            for alias in doc.aliases:
                alias_map[alias.lower()] = doc.slug
        return alias_map

    def _bm25_score(self, query_terms: list[str], idx: int) -> float:
        score = 0.0
        freqs = self.term_freqs[idx]
        doc_len = len(self.chunk_tokens[idx])
        k1 = 1.5
        b = 0.75
        for term in query_terms:
            tf = freqs.get(term, 0)
            if not tf:
                continue
            idf = self.idf.get(term, 0.0)
            denom = tf + k1 * (1 - b + b * doc_len / self.avg_doc_len)
            score += idf * (tf * (k1 + 1)) / denom
        return score

    def _tfidf_cosine_score(self, query_terms: list[str], idx: int) -> float:
        query_tf = Counter(query_terms)
        doc_tf = self.term_freqs[idx]
        numerator = 0.0
        query_norm = 0.0
        doc_norm = 0.0
        terms = set(query_tf) | set(doc_tf)
        for term in terms:
            idf = self.idf.get(term, 0.0)
            q_weight = query_tf.get(term, 0) * idf
            d_weight = doc_tf.get(term, 0) * idf
            numerator += q_weight * d_weight
            query_norm += q_weight * q_weight
            doc_norm += d_weight * d_weight
        if not query_norm or not doc_norm:
            return 0.0
        return numerator / math.sqrt(query_norm * doc_norm)

    def _course_boost(self, query: str, chunk: ContextualChunk) -> float:
        query_l = query.lower()
        boost = 0.0
        for alias, slug in self.course_alias_map.items():
            if alias and alias in query_l and slug == chunk.course_slug:
                boost += 1.0
        return min(boost, 2.5)

    def _section_boost(self, query_terms: set[str], chunk: ContextualChunk) -> float:
        section_terms = set(chunk.section.lower().replace("_", " ").split())
        if not section_terms:
            return 0.0
        return 0.2 * len(query_terms & section_terms)

    def _exact_phrase_boost(self, query: str, chunk: ContextualChunk) -> float:
        chunk_text = chunk.contextual_text.lower()
        boost = 0.0
        for phrase in _phrases(query):
            if phrase in chunk_text:
                boost += 0.15
        return min(boost, 1.0)

    def search(
        self, query: str, top_k: int = 5, candidate_k: int = 18
    ) -> list[dict[str, object]]:
        query_terms = _tokens(query)
        if not query_terms:
            return []
        query_term_set = set(query_terms)
        candidates = []
        for idx, chunk in enumerate(self.chunks):
            bm25 = self._bm25_score(query_terms, idx)
            semantic = self._tfidf_cosine_score(query_terms, idx)
            hybrid = (0.65 * bm25) + (0.35 * semantic)
            if hybrid > 0:
                candidates.append((idx, hybrid, bm25, semantic))
        candidates.sort(key=lambda item: item[1], reverse=True)

        reranked = []
        for idx, hybrid, bm25, semantic in candidates[:candidate_k]:
            chunk = self.chunks[idx]
            rerank_score = (
                hybrid
                + self._course_boost(query, chunk)
                + self._section_boost(query_term_set, chunk)
                + self._exact_phrase_boost(query, chunk)
            )
            reranked.append((chunk, rerank_score, hybrid, bm25, semantic))
        reranked.sort(key=lambda item: item[1], reverse=True)

        return [
            {
                "chunk_id": chunk.chunk_id,
                "course": chunk.course,
                "section": chunk.section,
                "source_url": chunk.source_url,
                "score": round(score, 4),
                "hybrid_score": round(hybrid, 4),
                "bm25_score": round(bm25, 4),
                "semantic_score": round(semantic, 4),
                "context": chunk.context,
                "text": chunk.text,
            }
            for chunk, score, hybrid, bm25, semantic in reranked[:top_k]
        ]


_DEFAULT_RETRIEVER: BCRECCourseRetriever | None = None


def get_bcrec_course_retriever() -> BCRECCourseRetriever:
    global _DEFAULT_RETRIEVER
    if _DEFAULT_RETRIEVER is None:
        _DEFAULT_RETRIEVER = BCRECCourseRetriever()
    return _DEFAULT_RETRIEVER


def search_bcrec_course_details(query: str, top_k: int = 5) -> str:
    """Return voice-agent-friendly detailed context for a BCREC course question."""
    results = get_bcrec_course_retriever().search(query, top_k=top_k)
    if not results:
        return (
            "No matching BCREC course context found. Ask for a clearer stream or topic."
        )
    blocks = []
    for index, item in enumerate(results, start=1):
        blocks.append(
            "\n".join(
                [
                    f"Result {index}: {item['course']} - {item['section']}",
                    f"Source: {item['source_url']}",
                    f"Relevance score: {item['score']}",
                    str(item["text"]),
                ]
            )
        )
    return "\n\n".join(blocks)


if __name__ == "__main__":
    import sys

    query = " ".join(sys.argv[1:]) or "AI ML career pathways and labs"
    print(search_bcrec_course_details(query))
