// Shared low-risk UX fixes that replace page-local inline handlers.
document.addEventListener("DOMContentLoaded", function(){
  var searchInput = document.getElementById("jh404-input");
  var searchButton = document.getElementById("jh404-search-button");
  function run404Search(){
    if(!searchInput) return;
    var q = searchInput.value.trim();
    if(q) window.location = "/ebooks/?q=" + encodeURIComponent(q);
  }
  if(searchButton){
    searchButton.addEventListener("click", run404Search);
  }
  if(searchInput){
    searchInput.addEventListener("keydown", function(event){
      if(event.key === "Enter"){
        event.preventDefault();
        run404Search();
      }
    });
  }

  var backToTop = document.getElementById("bttBtn");
  if(backToTop){
    backToTop.addEventListener("click", function(){
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }
});
