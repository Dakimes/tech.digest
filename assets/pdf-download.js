(function(){
  function injectButton(){
    if(document.querySelector('.pdf-download')){ return; }
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'pdf-download';
    button.setAttribute('aria-label', 'Скачать страницу в PDF');
    button.innerHTML = '\n      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">\n        <path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm8 1.5V8h4.5L14 3.5zM8.75 10.5h2.25a1.75 1.75 0 1 1 0 3.5H9.5V16H8V10.5h.75zm.75 2h1.25a.75.75 0 1 0 0-1.5H9.5v1.5zm5-2c.966 0 1.75.784 1.75 1.75V16h-1.5v-.5h-2.5V16H11.5v-3.75c0-.966.784-1.75 1.75-1.75zm0 1.5H13.25a.25.25 0 0 0-.25.25v1.25h2.5v-1.25a.25.25 0 0 0-.25-.25zM8 18h8v1.5H8V18z"/>\n      </svg>\n      <span>Скачать PDF</span>\n    ';
    button.addEventListener('click', function(){
      window.print();
    });
    document.body.appendChild(button);
  }

  function prepareLazyImages(){
    var lazyImages = document.querySelectorAll('img[loading="lazy"]');
    Array.prototype.forEach.call(lazyImages, function(img){
      if(!img.dataset){ return; }
      if(!img.dataset.wasLazy){ img.dataset.wasLazy = 'true'; }
      try{
        img.loading = 'eager';
      } catch(err){
        img.removeAttribute('loading');
      }
      if(typeof img.decode === 'function'){
        img.decode().catch(function(){});
      } else if(img.complete !== true){
        var preload = new Image();
        preload.src = img.currentSrc || img.src;
      }
    });
  }

  function restoreLazyImages(){
    var prepared = document.querySelectorAll('img[data-was-lazy]');
    Array.prototype.forEach.call(prepared, function(img){
      try{
        img.loading = 'lazy';
      } catch(err){
        if(img.dataset){ delete img.dataset.wasLazy; }
        return;
      }
      if(img.dataset){ delete img.dataset.wasLazy; }
    });
  }

  if(document.readyState === 'loading'){
    document.addEventListener('DOMContentLoaded', injectButton);
  } else {
    injectButton();
  }

  if(typeof window !== 'undefined'){
    window.addEventListener('beforeprint', prepareLazyImages);
    window.addEventListener('afterprint', restoreLazyImages);
    if(window.matchMedia){
      var mediaQuery = window.matchMedia('print');
      if(typeof mediaQuery.addEventListener === 'function'){
        mediaQuery.addEventListener('change', function(event){
          if(event.matches){
            prepareLazyImages();
          } else {
            restoreLazyImages();
          }
        });
      } else if(typeof mediaQuery.addListener === 'function'){
        mediaQuery.addListener(function(event){
          if(event.matches){
            prepareLazyImages();
          } else {
            restoreLazyImages();
          }
        });
      }
    }
  }
})();
