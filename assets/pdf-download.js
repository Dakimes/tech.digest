(function(){
  var activeButton = null;
  var supportsPromise = typeof Promise === 'function';

  function waitForImage(img){
    if(img.complete && img.naturalWidth !== 0){
      return Promise.resolve();
    }
    if(typeof img.decode === 'function'){
      return img.decode().catch(function(){
        if(img.complete){ return; }
        return new Promise(function(resolve){
          var done = function(){
            img.removeEventListener('load', done);
            img.removeEventListener('error', done);
            resolve();
          };
          img.addEventListener('load', done, { once: true });
          img.addEventListener('error', done, { once: true });
        });
      });
    }
    return new Promise(function(resolve){
      if(img.complete){
        resolve();
        return;
      }
      var done = function(){
        img.removeEventListener('load', done);
        img.removeEventListener('error', done);
        resolve();
      };
      img.addEventListener('load', done, { once: true });
      img.addEventListener('error', done, { once: true });
    });
  }

  function prepareLazyImages(){
    var lazyImages = document.querySelectorAll('img[loading="lazy"], img[data-was-lazy]');
    var waits = supportsPromise ? [] : null;
    Array.prototype.forEach.call(lazyImages, function(img){
      if(!img.hasAttribute('data-was-lazy')){
        img.setAttribute('data-was-lazy', 'true');
        try{
          img.loading = 'eager';
        } catch(err){
          img.setAttribute('loading', 'eager');
        }
      }
      if(waits){
        waits.push(waitForImage(img));
      } else if(img.complete !== true){
        var preload = new Image();
        preload.src = img.currentSrc || img.src;
      }
    });
    if(!waits){ return null; }
    return Promise.all(waits).then(function(){ return undefined; });
  }

  function restoreLazyImages(){
    var prepared = document.querySelectorAll('img[data-was-lazy]');
    Array.prototype.forEach.call(prepared, function(img){
      try{
        img.loading = 'lazy';
      } catch(err){
        img.setAttribute('loading', 'lazy');
      }
      img.removeAttribute('data-was-lazy');
    });
  }

  function setButtonState(button, isBusy){
    if(!button){ return; }
    if(isBusy){
      activeButton = button;
      button.disabled = true;
      button.setAttribute('aria-busy', 'true');
      button.classList.add('is-loading');
    } else {
      if(activeButton === button){ activeButton = null; }
      button.disabled = false;
      button.removeAttribute('aria-busy');
      button.classList.remove('is-loading');
    }
  }

  function injectButton(){
    if(document.querySelector('.pdf-download')){ return; }
    var button = document.createElement('button');
    button.type = 'button';
    button.className = 'pdf-download';
    button.setAttribute('aria-label', 'Скачать страницу в PDF');
    button.innerHTML = '\n      <svg viewBox="0 0 24 24" aria-hidden="true" focusable="false">\n        <path d="M6 2h9l5 5v13a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2zm8 1.5V8h4.5L14 3.5zM8.75 10.5h2.25a1.75 1.75 0 1 1 0 3.5H9.5V16H8V10.5h.75zm.75 2h1.25a.75.75 0 1 0 0-1.5H9.5v1.5zm5-2c.966 0 1.75.784 1.75 1.75V16h-1.5v-.5h-2.5V16H11.5v-3.75c0-.966.784-1.75 1.75-1.75zm0 1.5H13.25a.25.25 0 0 0-.25.25v1.25h2.5v-1.25a.25.25 0 0 0-.25-.25zM8 18h8v1.5H8V18z"/>\n      </svg>\n      <span>Скачать PDF</span>\n    ';
    button.addEventListener('click', function(){
      if(button.disabled){ return; }
      var preparation = prepareLazyImages();
      if(!preparation || typeof preparation.then !== 'function'){
        window.print();
        return;
      }
      setButtonState(button, true);
      preparation.then(function(){
        if(typeof requestAnimationFrame === 'function'){
          return new Promise(function(resolve){
            requestAnimationFrame(function(){ requestAnimationFrame(resolve); });
          });
        }
        return undefined;
      }).then(function(){
        window.print();
      }).catch(function(){
        restoreLazyImages();
        setButtonState(button, false);
      });
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
    window.addEventListener('beforeprint', function(){
      prepareLazyImages();
    });
    window.addEventListener('afterprint', function(){
      restoreLazyImages();
      if(activeButton){
        setButtonState(activeButton, false);
      }
    });
    if(window.matchMedia){
      var mediaQuery = window.matchMedia('print');
      var handler = function(event){
        if(event.matches){
          prepareLazyImages();
        } else {
          restoreLazyImages();
        }
      };
      if(typeof mediaQuery.addEventListener === 'function'){
        mediaQuery.addEventListener('change', handler);
      } else if(typeof mediaQuery.addListener === 'function'){
        mediaQuery.addListener(handler);
      }
    }
  }
})();
