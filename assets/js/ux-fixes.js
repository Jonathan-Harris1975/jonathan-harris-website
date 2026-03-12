
// Auto add alt text if missing
document.addEventListener("DOMContentLoaded",function(){
  document.querySelectorAll("img").forEach(function(img){
    if(!img.hasAttribute("alt") || img.getAttribute("alt").trim()===""){
      let name = img.src.split("/").pop().replace(/[-_]/g," ").replace(/\..+$/,"");
      img.setAttribute("alt",name);
    }
  });
});
