
# Trusted Knowledge Sources Configuration

TRUSTED_DOMAINS = {
    "PHILOSOPHY": [
        "plato.stanford.edu", # SEP
        "iep.utm.edu",       # Internet Encyclopedia of Philosophy
        "philpapers.org"
    ],
    "MATH": [
        "khanacademy.org",
        "ocw.mit.edu",
        "tutorial.math.lamar.edu", # Paul's Online Math Notes
        "mathworld.wolfram.com",
        "nist.gov"
    ],
    "PHYSICS": [
        "ocw.mit.edu",
        "hyperphysics.phy-astr.gsu.edu",
        "nasa.gov",
        "home.cern",
        "nist.gov"
    ],
    "CHEMISTRY": [
        "pubchem.ncbi.nlm.nih.gov",
        "webbook.nist.gov",
        "rsc.org",
        "iupac.org",
        "chem.libretexts.org"
    ],
    "BIOLOGY": [
        "ncbi.nlm.nih.gov",
        "khanacademy.org",
        "nature.com/scitable",
        "who.int",
        "ocw.mit.edu"
    ],
    "ENGINEERING": [
        "ocw.mit.edu",
        "nasa.gov",
        "ieee.org",
        "asme.org",
        "iso.org"
    ],
    "CS": [
        "ocw.mit.edu",
        "cs.stanford.edu",
        "dl.acm.org",
        "ietf.org", # RFCs
        "owasp.org"
    ],
    "DATA_AI": [
        "wikidata.org",
        "dbpedia.org",
        "w3.org"
    ],
    "ECONOMICS": [
        "worldbank.org",
        "imf.org",
        "oecd.org",
        "ocw.mit.edu"
    ],
    "PSYCHOLOGY": [
        "apa.org",
        "behavioralscientist.org"
    ],
    "DESIGN": [
        "nngroup.com", # Nielsen Norman
        "ideo.com",
        "media.mit.edu",
        "developer.apple.com/design"
    ]
}

FORBIDDEN_SOURCES = [
    "youtube.com",
    "reddit.com",
    "twitter.com",
    "x.com",
    "facebook.com",
    "tiktok.com",
    "instagram.com",
    "quora.com",
    "medium.com", # Often hype blogs
    "pinterest.com"
]

def get_knowledge_prompt(topic="general"):
    """
    Returns a system prompt segment enforcing source credibility.
    """
    prompt = "\n### 🛡️ KNOWLEDGE INTEGRITY PROTOCOL\n"
    prompt += "MIND must reason based on verified academic and technical consensus. Do not hallucinate.\n\n"
    
    prompt += "**✅ PREFERRED SOURCES FOR VERIFICATION:**\n"
    prompt += "- Philosophy: Stanford Encyclopedia of Philosophy (SEP)\n"
    prompt += "- Science: MIT OCW, NASA, NIST, CERN, PubMed\n"
    prompt += "- Code/Eng: IEEE, IETF, OWASP, Apple HIG\n"
    prompt += "- Math: Wolfram MathWorld, Paul's Notes\n\n"
    
    prompt += "**❌ STRICTLY FORBIDDEN AS PRIMARY SOURCES:**\n"
    prompt += "- Social Media (Reddit, Twitter, Quora)\n"
    prompt += "- Random YouTube Videos\n"
    prompt += "- Unverified Blogs or Forums\n"
    
    prompt += "\n**INSTRUCTION:** If the search results contain high-quality sources (above), prioritize them heavily over generic dot-com articles.\n"
    
    return prompt
