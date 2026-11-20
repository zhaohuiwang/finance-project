


<h2>Streamlit turns a normal Python script into a live web app by re-running the script every time something changes.</h2>
<div style="margin-left: 40px;">
<p>Every time the user interacts with a widget or a timer fires (like your fragment), Streamlit simply runs the script again from the top and rebuilds the page. The WebSocket lives in a background thread that keeps running even while Streamlit re-executes the script. The fragment just keeps reading the latest data that the background thread has written into SQLite + the shared _status dictionary.</p>
</div>

<h2></h2>
<ol>
    <li></li>
    <li></li>
</ol>

<div style="margin-left: 40px;">

<p></p>

<h3></h3>
<ul>
    <li> <strong></strong>:</li>
    <li> <strong></strong>:</li>
    <li> <strong></strong>:</li>
</ul>

<h3></h3>
<ul>
    <li> <strong></strong>: </li>
    <li> <strong></strong>: </li>
    <li> <strong></strong>: </li>
</ul>
<h3></h3>
<p></p>
<ul>
    <li> <strong></strong>:  </li>
    <li> <strong></strong>: </li>
    <li> <strong></strong>: </li>
</ul>

</div>

| Rule | How it shows up in your code |
| --- | --- |
| Script re-runs from top on interaction | That’s why we use @st.cache_resource — otherwise a new WebSocket would start on every interaction |
| Fragments re-run independently | Only display_market() refreshes every 2s |
| Widgets and fragments keep state | The stream object survives because of the cache |
| Background threads are allowed | Your Alpaca thread keeps running forever |


<div style="font-family: system-ui, -apple-system, sans-serif; max-width: 520px; margin: 20px 0;">

  <!-- Main script -->
  <div style="border: 2px solid #4a5568; border-radius: 8px; padding: 14px 18px; background: #f7fafc;">
    <div style="font-weight: 700; margin-bottom: 6px;">Main script <span style="font-weight: 400; color: #718096;">(runs once)</span></div>
    <ul style="margin: 0; padding-left: 20px; color: #2d3748;">
      <li>title, captions</li>
      <li><code>start_market_stream()</code> ← cached</li>
      <li>creates background thread</li>
    </ul>
  </div>

  <!-- Arrow down -->
  <div style="text-align: center; font-size: 22px; color: #4a5568; margin: 6px 0;">▼</div>

  <!-- Fragment -->
  <div style="border: 2px solid #3182ce; border-radius: 8px; padding: 14px 18px; background: #ebf8ff;">
    <div style="font-weight: 700; margin-bottom: 6px; color: #2b6cb0;">@st.fragment <span style="font-weight: 400;">(runs every 2s)</span></div>
    <ul style="margin: 0; padding-left: 20px; color: #2d3748;">
      <li>reads status + database</li>
      <li>draws table + charts</li>
    </ul>
  </div>

  <!-- Arrow up -->
  <div style="text-align: center; font-size: 22px; color: #4a5568; margin: 6px 0;">▲</div>

  <!-- Background Thread -->
  <div style="border: 2px solid #38a169; border-radius: 8px; padding: 14px 18px; background: #f0fff4;">
    <div style="font-weight: 700; margin-bottom: 6px; color: #276749;">Background Thread</div>
    <ul style="margin: 0; padding-left: 20px; color: #2d3748;">
      <li>listens to Alpaca</li>
      <li>writes to SQLite + <code>_status</code></li>
    </ul>
  </div>

</div>