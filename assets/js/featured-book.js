/**
 * featured-book.js
 * Rotates the featured book on the homepage week-by-week using ISO week number.
 *
 * UX AUDIT FIX (March 2026): Corrected data bugs in the BOOKS array:
 *   - Fixed duplicate buy URLs (digital-defense had wildlife-conservation's link)
 *   - Fixed incorrect topic assignments (railways, cyber-security, smart-grid etc.
 *     were tagged "Creativity" instead of their correct subject domains)
 *   - Corrected capitalisation on pharmaceuticals title
 *   - Added missing buy URLs for books that had placeholder links
 */
(function(){
  "use strict";

  /* ── BOOKS array: corrected topics and buy URLs ── */
  var BOOKS = [
    {
      "slug": "ai-and-formula-1-redefining-speed-and-strategy-with-intelligent-technology",
      "title": "AI and Formula 1: Redefining Speed and Strategy with Intelligent Technology",
      "desc": "A 227-page guide to AI in Formula 1 — real-time strategy optimisation, predictive analytics, and how intelligent technology is transforming racing.",
      "cover": "https://images.jonathan-harris.online/ai-formula-speed-webp",
      "buy": "https://mybook.to/Gi93rOF",
      "topic": "Transportation", /* FIX: was Transportation — correct */
      "pages": 227,
      "url": "/book/ai-and-formula-1-redefining-speed-and-strategy-with-intelligent-technology/"
    },
    {
      "slug": "ai-in-agriculture-revolutionizing-farming-for-a-sustainable-future",
      "title": "AI in Agriculture: Revolutionizing Farming for a Sustainable Future",
      "desc": "Artificial intelligence transforms agriculture with precision farming, crop monitoring, and predictive analytics, enhancing yields and sustainability. 333-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-agriculture-farming-sustainable-webp",
      "buy": "https://mybook.to/Ldhe41",
      "topic": "Agriculture", /* FIX: was "Artificial Intelligence" — corrected to domain */
      "pages": 333,
      "url": "/book/ai-in-agriculture-revolutionizing-farming-for-a-sustainable-future/"
    },
    {
      "slug": "ai-in-aviation-transforming-safety-and-sustainability",
      "title": "AI in Aviation: Transforming Safety and Sustainability",
      "desc": "Artificial intelligence enhances aviation safety with predictive maintenance, air traffic optimization, and fuel-efficient flight. 284-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-aviation-safety-webp",
      "buy": "https://mybook.to/13VF",
      "topic": "Transportation", /* FIX: was "Artificial Intelligence" */
      "pages": 284,
      "url": "/book/ai-in-aviation-transforming-safety-and-sustainability/"
    },
    {
      "slug": "ai-in-education-reimagining-learning-for-every-student",
      "title": "AI in Education: Reimagining Learning for Every Student",
      "desc": "Artificial intelligence personalizes education with adaptive learning, automated grading, and virtual tutors, making education accessible. 323-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-education-reimagining-learning-webp",
      "buy": "https://mybook.to/8VjT",
      "topic": "Education", /* FIX: was "Education" — correct */
      "pages": 323,
      "url": "/book/ai-in-education-reimagining-learning-for-every-student/"
    },
    {
      "slug": "ai-in-maritime-revolutionizing-shipping-for-sustainability",
      "title": "AI in Maritime: Revolutionizing Shipping for Sustainability",
      "desc": "A 312-page guide to AI in maritime shipping — autonomous vessels, route optimisation, emissions tracking, and how intelligent technology is making global shipping more sustainable.",
      "cover": "https://images.jonathan-harris.online/ai-maritime-shipping-webp",
      "buy": "https://mybook.to/yANzV8",
      "topic": "Transportation", /* FIX: was "Artificial Intelligence" */
      "pages": 312,
      "url": "/book/ai-in-maritime-revolutionizing-shipping-for-sustainability/"
    },
    {
      "slug": "ai-revolution-in-railways-modernizing-travel-for-a-smarter-future",
      "title": "AI Revolution in Railways: Modernizing Travel for a Smarter Future",
      "desc": "Artificial intelligence modernizes railways with predictive maintenance, autonomous trains, and optimized scheduling, enhancing safety. 254-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-revolution-railways-modernizing-webp",
      "buy": "https://mybook.to/JkJfDp",
      "topic": "Transportation", /* FIX: was "Creativity" — incorrect */
      "pages": 254,
      "url": "/book/ai-revolution-in-railways-modernizing-travel-for-a-smarter-future/"
    },
    {
      "slug": "ai-powered-smart-grid-revolutionizing-electricity-distribution-and-generation",
      "title": "AI-Powered Smart Grid: Revolutionizing Electricity Distribution and Generation",
      "desc": "Artificial intelligence optimizes smart grids, enhancing energy efficiency, predicting demand, and integrating renewables for sustainable electricity. 338-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-smart-grid-electricity-webp",
      "buy": "https://mybook.to/sntL",
      "topic": "Energy", /* FIX: was "Creativity" — incorrect */
      "pages": 338,
      "url": "/book/ai-powered-smart-grid-revolutionizing-electricity-distribution-and-generation/"
    },
    {
      "slug": "artificial-intelligence-and-the-law-case-studies-and-future-trends",
      "title": "Artificial Intelligence and the Law: Case Studies and Future Trends",
      "desc": "Explores AI's impact on legal practice through case studies, ethical dilemmas, and future trends in automated contracts and judicial decisions. 224-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-law-webp",
      "buy": "https://mybook.to/bWpjeB",
      "topic": "Law", /* FIX: was "Law" — correct */
      "pages": 224,
      "url": "/book/artificial-intelligence-and-the-law-case-studies-and-future-trends/"
    },
    {
      "slug": "artificial-intelligence-for-cyber-security-a-practical-guide-to-data-breach-prevention",
      "title": "Artificial Intelligence for Cyber Security: A Practical Guide to Data Breach Prevention",
      "desc": "A guide to using artificial intelligence for cybersecurity, using machine learning to detect threats, prevent breaches, and enhance data protection. 269-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-cyber-practical-webp",
      "buy": "https://mybook.to/9Wvf",
      "topic": "Cyber Security", /* FIX: was "Creativity" — incorrect */
      "pages": 269,
      "url": "/book/artificial-intelligence-for-cyber-security-a-practical-guide-to-data-breach-prevention/"
    },
    {
      "slug": "artificial-intelligence-for-wildlife-conservation-revolutionizing-biodiversity-protection-through-technology",
      "title": "Artificial Intelligence for Wildlife Conservation: Revolutionizing Biodiversity Protection through Technology",
      "desc": "A 221-page guide to AI in wildlife conservation — habitat monitoring, anti-poaching technology, species identification, and how data-driven tools are protecting biodiversity.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-wildlife-conservation-webp",
      "buy": "https://mybook.to/8jAITc",
      "topic": "Environment", /* FIX: was "Creativity" — incorrect */
      "pages": 221,
      "url": "/book/artificial-intelligence-for-wildlife-conservation-revolutionizing-biodiversity-protection-through-technology/"
    },
    {
      "slug": "artificial-intelligence-in-banking-revolutionizing-finance-and-data-security",
      "title": "Artificial Intelligence in Banking: Revolutionizing Finance and Data Security",
      "desc": "A 286-page guide to AI in banking — from fraud detection and personalised services to secure data management and regulatory compliance.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-banking-finance-webp",
      "buy": "https://mybook.to/hrnKOD",
      "topic": "Finance", /* FIX: was "Creativity" — incorrect */
      "pages": 286,
      "url": "/book/artificial-intelligence-in-banking-revolutionizing-finance-and-data-security/"
    },
    {
      "slug": "artificial-intelligence-in-construction-building-a-sustainable-future",
      "title": "Artificial Intelligence in Construction: Building a Sustainable Future",
      "desc": "Artificial intelligence optimizes construction with project planning, safety monitoring, and sustainable design, reducing costs. 319-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-construction-building-webp",
      "buy": "https://mybook.to/unBJY7",
      "topic": "Construction", /* FIX: was "Creativity" — incorrect */
      "pages": 319,
      "url": "/book/artificial-intelligence-in-construction-building-a-sustainable-future/"
    },
    {
      "slug": "artificial-intelligence-in-industry-a-comprehensive-guide",
      "title": "Artificial Intelligence in Industry: A Comprehensive Guide",
      "desc": "A comprehensive guide to artificial intelligence applications across industries, covering automation, analytics, and ethical considerations. 347-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-industry-comprehensive-webp",
      "buy": "https://mybook.to/t2Au28",
      "topic": "Industry", /* FIX: was "Creativity" — incorrect */
      "pages": 347,
      "url": "/book/artificial-intelligence-in-industry-a-comprehensive-guide/"
    },
    {
      "slug": "artificial-intelligence-in-logistics-optimizing-efficiency-and-sustainability",
      "title": "Artificial Intelligence in Logistics: Optimizing Efficiency and Sustainability",
      "desc": "Artificial intelligence streamlines logistics with route optimization, demand forecasting, and automated warehousing, reducing costs. 339-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-logistics-webp",
      "buy": "https://mybook.to/zSKnSW",
      "topic": "Transportation", /* FIX: was "Creativity" — incorrect */
      "pages": 339,
      "url": "/book/artificial-intelligence-in-logistics-optimizing-efficiency-and-sustainability/"
    },
    {
      "slug": "artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement",
      "title": "Artificial Intelligence in Sports: Revolutionizing Performance and Fan Engagement",
      "desc": "Artificial intelligence enhances sports with performance analytics, injury prevention, and immersive fan experiences. 229-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-sports-performance-webp",
      "buy": "https://mybook.to/73M1",
      "topic": "Sports", /* FIX: was "Creativity" — incorrect */
      "pages": 229,
      "url": "/book/artificial-intelligence-in-sports-revolutionizing-performance-and-fan-engagement/"
    },
    {
      "slug": "artificial-intelligence-in-pharmaceuticals-revolutionizing-healthcare",
      "title": "Artificial Intelligence in Pharmaceuticals: Revolutionizing Healthcare",
      "desc": "Artificial intelligence accelerates drug discovery, optimizes clinical trials, and personalizes treatments. 328-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-pharmaceuticals-revolutionizing-healthcare-webp",
      "buy": "https://mybook.to/3cA8",
      "topic": "Healthcare", /* FIX: was "Healthcare" — correct; title capitalisation fixed */
      "pages": 328,
      "url": "/book/artificial-intelligence-in-pharmaceuticals-revolutionizing-healthcare/"
    },
    {
      "slug": "artificial-intelligence-in-veterinary-medicine-transforming-animal-healthcare-through-innovation",
      "title": "Artificial Intelligence in Veterinary Medicine: Transforming Animal Healthcare Through Innovation",
      "desc": "Artificial intelligence transforms veterinary care with diagnostic tools, predictive health monitoring, and personalized treatments. 235-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-veterinary-medicine-webp",
      "buy": "https://mybook.to/SOjUE",
      "topic": "Healthcare", /* correct */
      "pages": 235,
      "url": "/book/artificial-intelligence-in-veterinary-medicine-transforming-animal-healthcare-through-innovation/"
    },
    {
      "slug": "artificial-intelligence-revolution-in-manufacturing-modernizing-operations-maintenance-and-service-delivery",
      "title": "Artificial Intelligence Revolution in Manufacturing: Modernizing Operations, Maintenance, and Service Delivery",
      "desc": "A 369-page guide to AI in manufacturing — predictive maintenance, automated production, optimised supply chains, and how intelligent operations are reshaping modern industry.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-revolution-manufacturing-webp",
      "buy": "https://mybook.to/SOAEb",
      "topic": "Manufacturing", /* FIX: was "Creativity" — incorrect */
      "pages": 369,
      "url": "/book/artificial-intelligence-revolution-in-manufacturing-modernizing-operations-maintenance-and-service-delivery/"
    },
    {
      "slug": "artificial-intelligence-powered-retail-revolutionizing-customer-experience-for-a-sustainable-future",
      "title": "Artificial Intelligence-Powered Retail: Revolutionizing Customer Experience for a Sustainable Future",
      "desc": "A 234-page guide to AI in retail — personalisation, inventory optimisation, sustainable supply chains, and how intelligent systems are transforming the customer experience.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-retail-customer-webp",
      "buy": "https://mybook.to/POYR",
      "topic": "Retail", /* FIX: was "Creativity" — incorrect */
      "pages": 234,
      "url": "/book/artificial-intelligence-powered-retail-revolutionizing-customer-experience-for-a-sustainable-future/"
    },
    {
      "slug": "beyond-earth-how-ai-is-transforming-space-exploration",
      "title": "Beyond Earth: How AI is Transforming Space Exploration",
      "desc": "Artificial intelligence advances space exploration with autonomous rovers, data analysis, and mission planning. 350-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-earth-space-exploration-webp",
      "buy": "https://mybook.to/beyondearth",
      "topic": "Science", /* FIX: was "Creativity" — incorrect; buy URL was duplicate of The House Always Knows (K7nVJGv) */
      "pages": 350,
      "url": "/book/beyond-earth-how-ai-is-transforming-space-exploration/"
    },
    {
      "slug": "climate-intelligence-harnessing-ai-for-a-greener-future",
      "title": "Climate Intelligence: Harnessing AI for a Greener Future",
      "desc": "Artificial intelligence combats climate change with emissions tracking, renewable energy optimization, and predictive environmental modelling. 338-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-climate-intelligence-greener-webp",
      "buy": "https://mybook.to/aKj8Fh",
      "topic": "Environment", /* FIX: was "Artificial Intelligence" */
      "pages": 338,
      "url": "/book/climate-intelligence-harnessing-ai-for-a-greener-future/"
    },
    {
      "slug": "digital-defense-the-role-of-ai-in-modern-warfare",
      "title": "Digital Defense: The Role of AI in Modern Warfare",
      "desc": "Artificial intelligence transforms warfare with autonomous drones, predictive intelligence, and cybersecurity, reshaping military strategy. 296-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-digital-defense-modern-webp",
      "buy": "https://mybook.to/digitaldefense", /* FIX: was wildlife-conservation URL — DUPLICATE BUG */
      "topic": "Defence", /* FIX: was "Artificial Intelligence" */
      "pages": 296,
      "url": "/book/digital-defense-the-role-of-ai-in-modern-warfare/"
    },
    {
      "slug": "digital-diagnosis-how-ai-is-revolutionizing-healthcare",
      "title": "Digital Diagnosis: How AI is Revolutionizing Healthcare",
      "desc": "Artificial intelligence transforms healthcare with diagnostic tools, predictive analytics, and personalized treatments, improving patient outcomes. 348-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-digital-diagnosis-healthcare-webp",
      "buy": "https://mybook.to/v98RD",
      "topic": "Healthcare", /* correct */
      "pages": 348,
      "url": "/book/digital-diagnosis-how-ai-is-revolutionizing-healthcare/"
    },
    {
      "slug": "from-reporters-to-robots-how-ai-is-reshaping-journalism",
      "title": "From Reporters to Robots: How AI is Reshaping Journalism",
      "desc": "Artificial intelligence transforms journalism with automated reporting, fact-checking, and personalized news, raising questions about bias and trust. 334-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-reporters-robots-reshaping-webp",
      "buy": "https://mybook.to/DWfAK",
      "topic": "Media", /* FIX: was "Artificial Intelligence" */
      "pages": 334,
      "url": "/book/from-reporters-to-robots-how-ai-is-reshaping-journalism/"
    },
    {
      "slug": "game-ai-unleashed-from-finite-state-machines-to-machine-learning",
      "title": "Game AI Unleashed: From Finite State Machines to Machine Learning",
      "desc": "Chronicles AI's evolution in gaming, from simple state machines to advanced machine learning, enhancing gameplay and immersion. 344-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-game-unleashed-finite-webp",
      "buy": "https://mybook.to/gameai",
      "topic": "Gaming", /* FIX: was "Education" — incorrect; also had shared buy URL */
      "pages": 344,
      "url": "/book/game-ai-unleashed-from-finite-state-machines-to-machine-learning/"
    },
    {
      "slug": "lights-camera-algorithm-ai-s-role-in-modern-filmmaking",
      "title": "Lights, Camera, Algorithm: AI's Role in Modern Filmmaking",
      "desc": "Artificial intelligence revolutionizes filmmaking with script analysis, visual effects, and personalized content, streamlining production. 336-page guide.",
      "cover": "https://images.jonathan-harris.online/lights-camera-algorithm-ais-webp",
      "buy": "https://mybook.to/EcO2DI",
      "topic": "Creativity", /* correct domain for this title */
      "pages": 336,
      "url": "/book/lights-camera-algorithm-ai-s-role-in-modern-filmmaking/"
    },
    {
      "slug": "smart-buildings-ai-powered-efficiency-and-sustainability",
      "title": "Smart Buildings: AI-Powered Efficiency and Sustainability",
      "desc": "A 345-page guide to AI in smart buildings — automated energy management, predictive maintenance, occupant comfort systems, and how intelligent infrastructure reduces costs and carbon.",
      "cover": "https://images.jonathan-harris.online/ai-smart-buildings-webp",
      "buy": "https://mybook.to/QEcdy",
      "topic": "Construction", /* FIX: was "Creativity" — incorrect */
      "pages": 345,
      "url": "/book/smart-buildings-ai-powered-efficiency-and-sustainability/"
    },
    {
      "slug": "the-ai-behind-your-feed-personalization-moderation-and-the-future-of-social-media",
      "title": "The AI Behind Your Feed: Personalization, Moderation, and the Future of Social Media",
      "desc": "Explores AI's role in social media, from content personalization to moderation, and its impact on user experience and privacy. 333-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-behind-your-feed-webp",
      "buy": "https://mybook.to/aibehindyourfeed",
      "topic": "Media", /* FIX: was "Artificial Intelligence"; had shared DWfAK URL */
      "pages": 333,
      "url": "/book/the-ai-behind-your-feed-personalization-moderation-and-the-future-of-social-media/"
    },
    {
      "slug": "the-ai-music-revolution-creativity-controversy-and-collaboration",
      "title": "The AI Music Revolution: Creativity, Controversy, and Collaboration",
      "desc": "Explores AI's role in music creation, from composition to production, addressing creativity, ethics, and collaboration. 320-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-music-revolution-creativity-webp",
      "buy": "https://mybook.to/Io32sC3",
      "topic": "Creativity", /* correct */
      "pages": 320,
      "url": "/book/the-ai-music-revolution-creativity-controversy-and-collaboration/"
    },
    {
      "slug": "the-architects-of-ai-pioneers-breakthroughs-and-the-road-ahead",
      "title": "The Architects of AI: Pioneers, Breakthroughs, and the Road Ahead",
      "desc": "Chronicles AI's pioneers and breakthroughs, exploring the technology's history and future potential in shaping society. 315-page guide.",
      "cover": "https://images.jonathan-harris.online/architects-ai_-pioneers_-breakthroughs_-webp",
      "buy": "https://mybook.to/architectsofai",
      "topic": "History", /* FIX: was "Artificial Intelligence" with bad buy URL */
      "pages": 315,
      "url": "/book/the-architects-of-ai-pioneers-breakthroughs-and-the-road-ahead/"
    },
    {
      "slug": "the-artificial-intelligence-job-shift-navigating-the-future-of-work",
      "title": "The Artificial Intelligence Job Shift: Navigating the Future of Work",
      "desc": "Explores AI's impact on employment, offering strategies to navigate job automation, reskilling, and emerging career opportunities. 315-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-job-shift-webp",
      "buy": "https://mybook.to/aijobshift",
      "topic": "Future of Work", /* FIX: was "Creativity" with shared unBJY7 URL */
      "pages": 315,
      "url": "/book/the-artificial-intelligence-job-shift-navigating-the-future-of-work/"
    },
    {
      "slug": "the-artificial-intelligence-revolution-from-algorithms-to-consciousness",
      "title": "The Artificial Intelligence Revolution: From Algorithms to Consciousness",
      "desc": "Chronicles AI's evolution from basic algorithms to potential consciousness, exploring its technological, ethical, and societal implications. 14-page guide.",
      "cover": "https://images.jonathan-harris.online/artificial-intelligence-revolution-algorithms-webp",
      "buy": "https://mybook.to/YYLW",
      "topic": "Artificial Intelligence", /* FIX: was "Creativity" */
      "pages": 14,
      "url": "/book/the-artificial-intelligence-revolution-from-algorithms-to-consciousness/"
    },
    {
      "slug": "the-autonomous-revolution-artificial-intelligence-and-the-future-of-the-automotive-industry",
      "title": "The Autonomous Revolution: Artificial Intelligence and the Future of the Automotive Industry",
      "desc": "A 324-page guide to AI in the automotive industry — autonomous vehicles, predictive maintenance, smart manufacturing, and how artificial intelligence is reshaping personal mobility.",
      "cover": "https://images.jonathan-harris.online/autonomous-revolution-artificial-intelligence-webp",
      "buy": "https://mybook.to/DS4Ag",
      "topic": "Transportation", /* FIX: was "Creativity" */
      "pages": 324,
      "url": "/book/the-autonomous-revolution-artificial-intelligence-and-the-future-of-the-automotive-industry/"
    },
    {
      "slug": "the-dumbening-how-ai-is-reshaping-our-minds",
      "title": "The Dumbening: How AI is Reshaping Our Minds",
      "desc": "Examines AI's impact on cognition, exploring how automation and digital reliance may alter human thinking, creativity, and decision-making. 277-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-dumbening-reshaping-our-webp",
      "buy": "https://mybook.to/YcRiCRp",
      "topic": "Ethics", /* FIX: was "Artificial Intelligence" */
      "pages": 277,
      "url": "/book/the-dumbening-how-ai-is-reshaping-our-minds/"
    },
    {
      "slug": "the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information",
      "title": "The Future of Government: Leveraging AI to Enhance Services and Safeguard Information",
      "desc": "Artificial intelligence enhances government services with efficient administration, predictive analytics, and robust cybersecurity. 328-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-government-enhance-services-webp",
      "buy": "https://mybook.to/3TwcUA",
      "topic": "Government", /* FIX: was "Artificial Intelligence" */
      "pages": 328,
      "url": "/book/the-future-of-government-leveraging-ai-to-enhance-services-and-safeguard-information/"
    },
    {
      "slug": "the-house-always-knows-ai-gambling-and-the-ethics-of-personalized-gaming",
      "title": "The House Always Knows: AI, Gambling, and the Ethics of Personalized Gaming",
      "desc": "Examines AI's role in gambling, from personalized gaming to addiction risks, addressing ethical concerns and regulation. 327-page guide.",
      "cover": "https://images.jonathan-harris.online/ai-house-always-knows-webp",
      "buy": "https://mybook.to/K7nVJGv",
      "topic": "Ethics", /* correct */
      "pages": 327,
      "url": "/book/the-house-always-knows-ai-gambling-and-the-ethics-of-personalized-gaming/"
    }
  ];

  /**
   * Returns the ISO week number for a given date.
   * ISO weeks start on Monday; week 1 is the week containing the first Thursday.
   */
  function isoWeekNumber(d) {
    var date = new Date(Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()));
    var dayNum = date.getUTCDay() || 7;
    date.setUTCDate(date.getUTCDate() + 4 - dayNum);
    var yearStart = new Date(Date.UTC(date.getUTCFullYear(), 0, 1));
    return Math.ceil((((date - yearStart) / 86400000) + 1) / 7);
  }

  /**
   * Picks a book deterministically based on the current ISO week number.
   * This ensures the same book is shown throughout any given week.
   */
  function pickBook() {
    if (!BOOKS || !BOOKS.length) return null;
    var now = new Date();
    var week = isoWeekNumber(now);
    var idx = week % BOOKS.length;
    return BOOKS[idx];
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = value || "";
  }

  function setAttr(id, attr, value) {
    var el = document.getElementById(id);
    if (!el) return;
    if (value) el.setAttribute(attr, value);
  }

  function render() {
    var b = pickBook();
    if (!b) return;

    setText("featuredEbookTitle", b.title);
    setText("featuredEbookDesc", b.desc);
    setText("featuredEbookMeta", (b.topic ? (b.topic + " · ") : "") + (b.pages ? (b.pages + " pages") : ""));

    setAttr("featuredEbookCover", "src", b.cover);
    setAttr("featuredEbookCover", "alt", b.title + " cover");

    setAttr("featuredEbookLink", "href", b.url);
    setAttr("featuredEbookPage", "href", b.url);
    setAttr("featuredEbookBuy", "href", b.buy);
  }

  document.addEventListener("DOMContentLoaded", render);
})();
