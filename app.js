(() => {
  "use strict";
  const cameras = [];
  const alerts = [];
  const categories = [];
  const zones = [];
  const chartSets = {
    "24h":{title:"Video-derived line crossings · last 24 hours",total:"—",peak:"—",values:[],axis:[]},
    "7d":{title:"Video-derived line crossings · last 7 days",total:"—",peak:"—",values:[],axis:[]},
    "30d":{title:"Video-derived line crossings · last 30 days",total:"—",peak:"—",values:[],axis:[]}
  };
  const fmt=new Intl.NumberFormat("en-US");
  const $=(s,r=document)=>r.querySelector(s);
  const $$=(s,r=document)=>[...r.querySelectorAll(s)];
  let activeFilter="all", localVideoUrl=null, toastTimer=null;

  function esc(v){return String(v).replace(/[&<>"']/g,c=>({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));}
  function showToast(message){const t=$("#toast");t.textContent=message;t.hidden=false;clearTimeout(toastTimer);toastTimer=setTimeout(()=>t.hidden=true,2800);}
  function closeMobileNav(){$("#sidebar").classList.remove("open");$("#mobile-scrim").hidden=true;$("#menu-toggle").setAttribute("aria-expanded","false");$("#menu-toggle").setAttribute("aria-label","Open navigation");}
  function setPage(name,hash=true){
    const target=$('[data-page="'+name+'"]');if(!target)return;
    $$(".page-section").forEach(s=>{const active=s===target;s.classList.toggle("active",active);s.hidden=!active;});
    $$(".nav-link").forEach(b=>{const active=b.dataset.nav===name;b.classList.toggle("active",active);if(active)b.setAttribute("aria-current","page");else b.removeAttribute("aria-current");});
    const title=target.querySelector("h1")?.textContent||"Overview";$("#page-crumb").textContent=title;document.title="TrafficMind | "+title;
    if(hash&&location.hash!=="#"+name)history.replaceState(null,"","#"+name);
    closeMobileNav();window.scrollTo({top:0,behavior:"smooth"});
  }
  function updateClock(){$("#current-time").textContent=new Intl.DateTimeFormat(undefined,{hour:"2-digit",minute:"2-digit"}).format(new Date());}
  function renderCameraRows(){return cameras.map(c=>'<div class="camera-row" data-camera-row="'+c.id+'" tabindex="0" role="button" aria-label="Select '+esc(c.name)+' configured camera"><span class="camera-thumb" aria-hidden="true">▧</span><span class="camera-info"><strong>'+esc(c.name)+'</strong><small>'+esc(c.zone)+'</small></span><span class="camera-status">'+esc(c.status)+'</span></div>').join("")||'<p class="empty-state">No cameras are configured. Uploaded video analysis does not imply a live camera connection.</p>';}
  function renderCameras(){
    $("#overview-cameras").innerHTML=renderCameraRows();$("#map-cameras").innerHTML=renderCameraRows();
    $$("[data-camera-row]").forEach(r=>{r.addEventListener("click",()=>selectCamera(r.dataset.cameraRow));r.addEventListener("keydown",e=>{if(e.key==="Enter"||e.key===" "){e.preventDefault();selectCamera(r.dataset.cameraRow);}});});
  }
  function selectCamera(id){
    const c=cameras.find(item=>item.id===id);if(!c)return;
    $("#map-selection").innerHTML='<span class="selection-label">CONFIGURED CAMERA</span><strong>'+esc(c.name)+'</strong><small>'+esc(c.status)+'</small>';
    $$(".map-marker").forEach(m=>m.setAttribute("aria-pressed",String(m.dataset.camera===id)));
  }
  function renderAlerts(){
    const open=alerts.filter(a=>!a.acknowledged).length;
    $("#sidebar-alert-count").textContent=open;$("#kpi-alerts").textContent=open;$("#alert-open-count").textContent=open;
    $("#overview-alerts").innerHTML=alerts.map(a=>'<div class="alert-row"><span class="alert-mark '+a.severity+'" aria-hidden="true">'+(a.severity==="critical"?"!":a.severity==="warning"?"△":"i")+'</span><span class="alert-text"><strong>'+esc(a.title)+'</strong><small>'+esc(a.location)+'</small></span><span class="alert-time">'+esc(a.time)+'</span></div>').join("")||'<p class="empty-state">No alerts from analyzed videos yet.</p>';
    const visible=alerts.filter(a=>activeFilter==="all"||a.severity===activeFilter);
    $("#alerts-list").innerHTML=visible.map(a=>'<div class="alert-full-row"><div class="alert-full-event"><span class="alert-mark '+a.severity+'" aria-hidden="true">'+(a.severity==="critical"?"!":a.severity==="warning"?"△":"i")+'</span><span class="alert-text"><strong>'+esc(a.title)+'</strong><small>'+esc(a.detail)+'</small></span></div><span class="alert-location">'+esc(a.location)+'</span><span class="alert-date">'+esc(a.time)+'</span><span class="severity-tag '+a.severity+'">'+esc(a.severity)+'</span><button type="button" class="ack-button '+(a.acknowledged?"acknowledged":"")+'" data-ack="'+a.id+'" '+(a.acknowledged?"disabled":"")+'>'+(a.acknowledged?"Acknowledged":"Acknowledge")+'</button></div>').join("");
    $("#alerts-empty").hidden=visible.length>0;$("#alerts-empty strong").textContent=alerts.length?"No alerts match this filter":"No video analysis alerts yet";$("#alerts-empty p").textContent=alerts.length?"Choose another severity to review alerts.":"Alerts appear when analyzed traffic meets a configured threshold.";
    $$("[data-ack]").forEach(b=>b.addEventListener("click",()=>{const a=alerts.find(x=>x.id===b.dataset.ack);if(a){a.acknowledged=true;renderAlerts();showToast("Demo alert acknowledged for this session.");}}));
  }
  function drawChart(svg,values,options={}){
    const w=options.width||720,h=options.height||215,p={top:13,right:10,bottom:14,left:22},pw=w-p.left-p.right,ph=h-p.top-p.bottom,high=Math.max(...values,10)*1.15;
    const x=i=>p.left+(values.length<2?.5:i/(values.length-1))*pw,y=v=>p.top+ph-(v/high)*ph;
    const pts=values.map((v,i)=>[x(i),y(v)]),line=pts.map((q,i)=>(i?"L":"M")+q[0].toFixed(1)+" "+q[1].toFixed(1)).join(" ");
    const area=line+" L"+x(values.length-1).toFixed(1)+" "+(p.top+ph)+" L"+x(0).toFixed(1)+" "+(p.top+ph)+" Z";
    const gid="fill-"+svg.id,grid=[0,1,2,3].map(i=>'<line class="chart-gridline" x1="'+p.left+'" y1="'+(p.top+i*ph/3)+'" x2="'+(w-p.right)+'" y2="'+(p.top+i*ph/3)+'"/>').join("");
    const circles=pts.map((q,i)=>'<circle class="chart-point" cx="'+q[0]+'" cy="'+q[1]+'" r="'+(values.length>15?2.4:3.5)+'" tabindex="0"><title>'+esc((options.labels&&options.labels[i])||("Sample interval "+(i+1)))+": "+fmt.format(values[i])+' illustrative vehicles</title></circle>').join("");
    svg.setAttribute("viewBox","0 0 "+w+" "+h);
    if(!values.length){svg.setAttribute("viewBox","0 0 "+w+" "+h);svg.innerHTML='<title>'+esc(options.title||"Video analysis chart")+'</title><desc>No analyzed video observations are available yet.</desc><text x="50%" y="50%" text-anchor="middle" dominant-baseline="middle" fill="#93a1b3" font-size="13">No video analysis data yet</text>';return;}
    svg.innerHTML='<title>'+esc(options.title||"Vehicle count chart")+'</title><desc>Data returned from locally analyzed video.</desc><defs><linearGradient id="'+gid+'" x1="0" x2="0" y1="0" y2="1"><stop offset="0%" stop-color="#448af6" stop-opacity=".20"/><stop offset="100%" stop-color="#448af6" stop-opacity="0"/></linearGradient></defs>'+grid+'<path class="chart-area" d="'+area+'" fill="url(#'+gid+')"/><path class="chart-line '+(options.forecast?"forecast":"")+'" d="'+line+'"/>'+circles;
  }
  function renderAnalytics(range="24h"){
    const d=chartSets[range]||chartSets["24h"];
    $("#analytics-chart-title").textContent=d.title;$("#analytics-volume").textContent=d.total;$("#analytics-total").textContent=d.total;$("#analytics-peak").textContent=d.peak;
    drawChart($("#analytics-chart"),d.values,{width:900,height:260,title:d.title});
    $("#analytics-axis").innerHTML=d.axis.map(x=>"<span>"+esc(x)+"</span>").join("");
    $(".analytics-chart-panel .chart-summary-label").textContent="video-derived line crossings";
  }
  function renderCategories(){
    $("#category-stats").innerHTML=categories.map(c=>'<div class="category-stat"><span class="category-icon '+c.color+'" aria-hidden="true">'+c.symbol+'</span><span><strong>'+c.name+'</strong><small>'+fmt.format(c.count)+' detected crossings</small></span><b>'+c.percent+'%</b></div>').join("")||'<p class="empty-state">Analyze a video to see detected vehicle categories.</p>';
    $("#zone-bars").innerHTML=zones.map(z=>'<div><div class="zone-bar-top"><span>'+z.name+'</span><strong>'+fmt.format(z.count)+'</strong></div><div class="zone-track"><i class="'+z.level+'" style="width:'+Math.round(z.count/Math.max(...zones.map(x=>x.count))*100)+'%"></i></div></div>').join("")||'<p class="empty-state">Analyze a video to see measured flow.</p>';
  }
  function renderCharts(){
    drawChart($("#overview-chart"),[],{width:720,height:215,title:"Video-derived line crossings over the last 24 hours"});
    renderAnalytics();
    drawChart($("#prediction-chart"),[],{width:900,height:260,title:"Forecast based on analyzed video",forecast:true});
  }
  function uploadMessage(msg,type=""){const n=$("#upload-message");n.textContent=msg;n.className="form-message"+(type?" "+type:"");}
  function videoError(message){
    if(!localVideoUrl){
      message="The optional sample video is unavailable in this checkout. Choose a video from your device instead.";
      $("#reset-video").disabled=true;uploadMessage(message,"error");
    } else uploadMessage("Preview failed. Try another supported video file.","error");
    $("#video-error-text").textContent=message;$("#video-empty").hidden=false;$("#video-state").textContent="Preview unavailable";
    $("#video-caption").textContent=localVideoUrl?"The selected video could not be previewed.":"Optional sample unavailable.";
    $("#system-video-status").textContent="Current preview unavailable";
  }
  function releaseVideo(){if(localVideoUrl){URL.revokeObjectURL(localVideoUrl);localVideoUrl=null;}}
  function loadVideo(file){
    if(!file)return;
    const ext=file.name.split(".").pop().toLowerCase(),allowed=["mp4","webm","ogv","ogg"],types=["video/mp4","video/webm","video/ogg"];
    if(file.size<=0)return uploadMessage("The selected file is empty. Choose a video file.","error");
    if(file.size>150*1024*1024)return uploadMessage("This file is over the 150 MB preview limit.","error");
    if(!allowed.includes(ext)||(file.type&&!types.includes(file.type)))return uploadMessage("Unsupported file. Choose an MP4, WebM, or Ogg video.","error");
    releaseVideo();localVideoUrl=URL.createObjectURL(file);
    const video=$("#traffic-video");video.pause();video.removeAttribute("src");video.querySelectorAll("source").forEach(s=>s.remove());video.src=localVideoUrl;video.load();
    $("#video-empty").hidden=true;$("#video-caption").textContent=file.name+" · local device preview";$("#video-state").textContent="Local preview selected";$("#system-video-status").textContent=" · user-selected local video";
    uploadMessage("Ready for local preview. This video has not been uploaded or analyzed.","success");
  }
  function restoreVideo(){
    releaseVideo();const video=$("#traffic-video");video.pause();video.removeAttribute("src");video.querySelectorAll("source").forEach(s=>s.remove());
    const source=document.createElement("source");source.src="assets/traffic.mp4";source.type="video/mp4";video.append(source);video.load();
    $("#video-empty").hidden=true;$("#video-caption").textContent="Optional sample clip";$("#video-state").textContent="Loading optional sample...";$("#system-video-status").textContent="";
    uploadMessage("Trying the optional local sample. If it is unavailable, choose a video from this device.");
  }
  function exportCsv(){
    const rows=[["TrafficMind local video analysis report"],["Data note","No video-derived results are available in direct-file mode. Open the local API dashboard to export persisted analysis."],["Metric","Value"],["Unique tracked vehicles","Not available"],["Average speed km/h","Not measured"],["Congestion proxy","Not available"],["Analysis alerts",String(alerts.length)]];
    const csv=rows.map(row=>row.map(cell=>'"'+String(cell??"").replaceAll('"','""')+'"').join(",")).join("\r\n");
    const blob=new Blob(["\ufeff",csv],{type:"text/csv;charset=utf-8"}),url=URL.createObjectURL(blob),link=document.createElement("a");
    link.href=url;link.download="trafficmind-analysis-report.csv";document.body.append(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);showToast("Empty-state report downloaded. Open the API dashboard for analyzed results.");
  }
  function searchMap(e){
    e.preventDefault();const input=$("#location-query"),query=input.value.trim(),msg=$("#location-message");
    if(!query){msg.textContent="Enter a place, pincode, or area to search.";msg.className="form-message error";input.focus();return;}
    $("#location-map").src="https://maps.google.com/maps?q="+encodeURIComponent(query)+"&t=&z=13&ie=UTF8&iwloc=&output=embed";
    msg.textContent="Map search updated using Google Maps. This service requires internet access.";msg.className="form-message success";
  }
  function init(){
    renderCameras();renderAlerts();renderCategories();renderCharts();updateClock();setInterval(updateClock,30000);
    $$(".nav-link").forEach(b=>b.addEventListener("click",()=>setPage(b.dataset.nav)));
    $$("[data-go]").forEach(b=>b.addEventListener("click",()=>setPage(b.dataset.go)));
    window.addEventListener("hashchange",()=>{const p=location.hash.slice(1);if($('[data-page="'+p+'"]'))setPage(p,false);});
    $("#menu-toggle").addEventListener("click",()=>{
      const open=!$("#sidebar").classList.contains("open");$("#sidebar").classList.toggle("open",open);$("#mobile-scrim").hidden=!open;
      $("#menu-toggle").setAttribute("aria-expanded",String(open));$("#menu-toggle").setAttribute("aria-label",open?"Close navigation":"Open navigation");if(open)$(".nav-link.active")?.focus();
    });
    $("#mobile-scrim").addEventListener("click",closeMobileNav);document.addEventListener("keydown",e=>{if(e.key==="Escape")closeMobileNav();});
    $$("[data-range]").forEach(b=>b.addEventListener("click",()=>{$$("[data-range]").forEach(x=>{x.classList.toggle("selected",x===b);x.setAttribute("aria-pressed",String(x===b));});renderAnalytics(b.dataset.range);}));
    $$("[data-filter]").forEach(b=>b.addEventListener("click",()=>{activeFilter=b.dataset.filter;$$("[data-filter]").forEach(x=>{x.classList.toggle("selected",x===b);x.setAttribute("aria-pressed",String(x===b));});renderAlerts();}));
    $$(".map-marker").forEach(b=>b.addEventListener("click",()=>selectCamera(b.dataset.camera)));
    $("#export-csv").addEventListener("click",exportCsv);$("#location-form").addEventListener("submit",searchMap);
    $("#video-upload").addEventListener("change",e=>{loadVideo(e.target.files?.[0]);e.target.value="";});
    $$("[data-upload-focus]").forEach(b=>b.addEventListener("click",()=>$("#video-upload").click()));
    $("#reset-video").addEventListener("click",restoreVideo);
    const drop=$("#upload-drop");
    ["dragenter","dragover"].forEach(type=>drop.addEventListener(type,e=>{e.preventDefault();drop.classList.add("dragging");}));
    ["dragleave","drop"].forEach(type=>drop.addEventListener(type,e=>{e.preventDefault();drop.classList.remove("dragging");}));
    drop.addEventListener("drop",e=>loadVideo(e.dataTransfer?.files?.[0]));
    $("#traffic-video").addEventListener("loadedmetadata",()=>{if(!localVideoUrl)$("#reset-video").disabled=false;});
    $("#traffic-video").addEventListener("loadedmetadata",()=>{$("#video-empty").hidden=true;$("#video-state").textContent="Preview ready";$("#system-video-status").textContent=localVideoUrl?" · user-selected local video":"";if(localVideoUrl)uploadMessage("Video loaded in this browser. No upload or analysis occurred.","success");});
    $("#traffic-video").addEventListener("error",()=>{videoError(localVideoUrl?"This browser cannot decode the selected file. Try an MP4 encoded with H.264 or a WebM video.":"The bundled MP4 may use a codec this browser cannot decode. Try choosing another local video.");if(localVideoUrl)uploadMessage("Preview failed. Try another supported video file.","error");});
    $("#location-query").addEventListener("input",()=>{const m=$("#location-message");if(m.classList.contains("error")){m.textContent="The search opens a Google Maps embed. No location is sent to TrafficMind.";m.className="form-message";}});
    const initial=location.hash.slice(1);setPage($('[data-page="'+initial+'"]')?initial:"overview",false);selectCamera("cam-central");
  }
  if(document.readyState==="loading")document.addEventListener("DOMContentLoaded",init,{once:true});else init();
})();
