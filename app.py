import streamlit as st
import instaloader
from datetime import datetime
import pytz
from collections import defaultdict

# ────────────────────────────────────────────────
# CONFIG & HELPERS
# ────────────────────────────────────────────────

IST = pytz.timezone('Asia/Kolkata')

def format_time(dt):
    return dt.strftime("%Y-%m-%d %I:%M %p IST") if dt else "N/A"

def safe_tagged_users(tagged):
    if not tagged:
        return "None"
    try:
        return ", ".join(tag.username for tag in tagged)
    except AttributeError:
        if isinstance(tagged, str):
            return tagged
        elif isinstance(tagged, (list, tuple)):
            return ", ".join(str(t) for t in tagged if t)
        else:
            return str(tagged)

# ────────────────────────────────────────────────
# ANALYSIS FUNCTIONS (unchanged)
# ────────────────────────────────────────────────

def analyze_reels(reels):
    if not reels:
        return None

    hour_stats = defaultdict(lambda: {'likes': [], 'comments': [], 'count': 0})

    for r in reels:
        if not r.get('date'):
            continue
        h = r['date'].hour
        hour_stats[h]['likes'].append(r['likes'] or 0)
        hour_stats[h]['comments'].append(r['comments'] or 0)
        hour_stats[h]['count'] += 1

    ranked_hours = []
    for h in sorted(hour_stats.keys()):
        s = hour_stats[h]
        if s['count'] > 0:
            avg_l = sum(s['likes']) / s['count']
            avg_c = sum(s['comments']) / s['count']
            ranked_hours.append((h, round(avg_l), round(avg_c), s['count']))

    ranked_hours.sort(key=lambda x: x[1] + 2 * x[2], reverse=True)

    return {
        'total_reels': len(reels),
        'avg_likes': round(sum(r['likes'] or 0 for r in reels) / len(reels)) if reels else 0,
        'avg_comments': round(sum(r['comments'] or 0 for r in reels) / len(reels)) if reels else 0,
        'ranked_hours': ranked_hours,
    }


def current_suggestion(now, analysis):
    if not analysis or analysis['total_reels'] < 1:
        return "Not enough data yet.\nGeneral tip: Afternoon (12–14) or evening (18:30–21:30) slots often work well for dance Reels in India."

    lines = []

    current_hour = now.hour
    ranked = analysis['ranked_hours']

    good_now = any(h <= current_hour <= h + 2 for h, _, _, _ in ranked)
    if good_now:
        lines.append("→ **RIGHT NOW** is inside one of your historically strong windows.")
    else:
        future_today = [h for h, _, _, _ in ranked if h > current_hour]
        if future_today:
            best_future = min(future_today)
            lines.append(f"Next strong window today: **{best_future:02d}:00 – {best_future+2:02d}:00 IST**")
        else:
            if ranked:
                best_tomorrow = ranked[0][0]
                lines.append(f"Strongest window tomorrow: **{best_tomorrow:02d}:00 – {best_tomorrow+2:02d}:00 IST**")
            else:
                lines.append("No clear pattern yet — try 12–14 or 18–21 IST.")

    lines.append(f"\nData confidence: **{'Medium' if analysis['total_reels'] >= 5 else 'Low'}** ({analysis['total_reels']} Reels)")
    lines.append(f"Average: **{analysis['avg_likes']} likes**, **{analysis['avg_comments']} comments** per Reel")

    return "\n".join(lines)

# ────────────────────────────────────────────────
# STREAMLIT APP - BEAUTIFUL UI
# ────────────────────────────────────────────────

st.set_page_config(page_title="Reel Timing Analyzer", page_icon="📈", layout="wide")

st.title("📈 Reel Timing Analyzer")
st.markdown("Fetch public Instagram Reels data → see raw details → get smart timing recommendations.")

# ──── INPUT SECTION ────
with st.container(border=True):
    col1, col2 = st.columns([3, 1])
    with col1:
        username = st.text_input(
            "Instagram Username (without @)",
            value="hyderabadancers",
            placeholder="e.g., hyderabadancers",
            help="Only public accounts work. No login required."
        )
    with col2:
        analyze_button = st.button("Analyze Now", type="primary", use_container_width=True, key="analyze")

if analyze_button and username.strip():
    with st.spinner("Fetching public Instagram data... (this may take a few seconds)"):
        try:
            L = instaloader.Instaloader()
            profile = instaloader.Profile.from_username(L.context, username)

            # ──── PART 1: PROFILE CARD ────
            st.subheader(f"Profile: @{profile.username}", divider="blue")
            col_profile_pic, col_profile_info = st.columns([1, 3])
            with col_profile_pic:
                st.image(profile.profile_pic_url, width=180, caption="Profile Picture")
            with col_profile_info:
                st.markdown(f"**Full name:** {profile.full_name or 'N/A'}")
                st.markdown(f"**Bio:**\n{profile.biography}")
                colf1, colf2, colf3 = st.columns(3)
                colf1.metric("Followers", f"{profile.followers:,}")
                colf2.metric("Following", f"{profile.followees:,}")
                colf3.metric("Total Posts", profile.mediacount)
                st.markdown(f"**External URL:** {profile.external_url or 'None'}")
                st.markdown(f"**Account Type:** {'Creator/Business' if profile.is_business_account else 'Personal'}")
                st.markdown(f"**Private:** {'Yes' if profile.is_private else 'No'}")

            # Account type suggestion if not professional
            if not profile.is_business_account:
                with st.expander("🚀 Unlock full insights — Switch to Creator Account", expanded=True):
                    st.info(
                        "Your account is currently Personal. Switch to **Creator** (free) to see:\n"
                        "- Views & plays per Reel\n"
                        "- Reach, saves, shares\n"
                        "- Audience active times (best upload hours)\n"
                        "- Detailed comments & engagement\n\n"
                        "**Steps (takes 30 seconds):**\n"
                        "1. Open Instagram app\n"
                        "2. Profile → Menu (three lines) → Settings and privacy\n"
                        "3. Account type and tools → Switch to professional account\n"
                        "4. Choose Creator → follow prompts\n"
                        "5. Go to Professional dashboard → Insights\n\n"
                        "After switching, come back here — the analysis will become **much more accurate**!"
                    )

            st.markdown("---")

            # ──── PART 2: VISIBLE REELS ────
            st.subheader("Visible Reels (Publicly Accessible)")
            posts_iter = profile.get_posts()
            reel_data = []
            reel_number = 0

            if not st.session_state.get("reels_loaded", False):
                for post in posts_iter:
                    if not post.is_video:
                        continue
                    reel_number += 1
                    likes = post.likes if post.likes is not None else 'N/A'
                    comm = post.comments if post.comments is not None else 'N/A'

                    with st.expander(f"🎥 Reel #{reel_number} ({post.shortcode})", expanded=(reel_number <= 3)):
                        col1, col2 = st.columns([1, 2])
                        with col1:
                            st.image(post.url, width=300, caption="Reel Preview")  # FIXED HERE
                        with col2:
                            st.markdown(f"**Upload time:** {format_time(post.date_local.astimezone(IST) if post.date_local else None)}")
                            col_likes, col_comm = st.columns(2)
                            col_likes.metric("Likes", likes)
                            col_comm.metric("Comments", comm)
                            st.markdown("**Caption:**")
                            st.markdown(post.caption or "No caption")
                            st.markdown(f"**Tagged users:** {safe_tagged_users(post.tagged_users)}")
                            st.markdown(f"**Hashtags:** {', '.join(post.caption_hashtags) if post.caption_hashtags else 'None'}")

                    reel_data.append({
                        'shortcode': post.shortcode,
                        'date': post.date_local.astimezone(IST) if post.date_local else None,
                        'likes': likes if isinstance(likes, (int, float)) else 0,
                        'comments': comm if isinstance(comm, (int, float)) else 0,
                    })

                st.session_state.reels_loaded = True
                st.success(f"Found **{reel_number} visible Reels** this cycle")

            # ──── PART 3: ANALYSIS ────
            st.markdown("---")
            st.subheader("Smart Analysis & Timing Recommendation")

            analysis = analyze_reels(reel_data)

            if analysis:
                col1, col2, col3 = st.columns(3)
                col1.metric("Reels Analyzed", analysis['total_reels'], help="Visible public Reels only")
                col2.metric("Average Likes", analysis['avg_likes'])
                col3.metric("Average Comments", analysis['avg_comments'])

                st.markdown("**Strongest time windows from your Reels**")
                for h, likes, comm, cnt in analysis['ranked_hours']:
                    st.markdown(f"- **{h:02d}:00 – {h+2:02d}:00** → {likes} likes, {comm} comments ({cnt} Reels)")

                st.markdown("**Recommendation right now**")
                st.info(current_suggestion(datetime.now(IST), analysis))
            else:
                st.warning("No Reels available yet for analysis.")

        except Exception as e:
            st.error(f"Error fetching data: {str(e)}")
            st.info("Tip: Instagram may rate-limit public access. Try again later, use mobile data, or switch to Creator account for full insights.")
else:
    st.info("Enter username and click Analyze Now to start.")
