// Script inject Ultra0: tra nhiều sản phẩm → tự chọn dùng thử miễn phí dài nhất → mở trang thanh toán ở luồng chính
var dexLoader=null, ctxRef=null, clientRef=null;
var PRODUCTS=["g1.play.20tb","g1.play.ai.pro","g1.30tb"];   // 5x / 20x (kèm dùng thử) / 20x (gói khác)
var PREFER="";        // Để trống = tự chọn dài nhất; có thể truyền "eft-12month" v.v.
function L(v){ Java.classFactory.loader=v; }
function S(o){ send(o); }

function periodRank(p){
  var m={"P1Y3M":15,"P1Y":12,"P12M":12,"P6M":6,"P4M":4,"P3M":3,"P2M":2,"P1M":1};
  return m[String(p)]||0;
}
function getActivity(){
  L(null);
  var found=null;
  try{
    var at=Java.use("android.app.ActivityThread").currentActivityThread();
    var m=at.mActivities.value;
    var it=m.values().iterator();
    var ACR=Java.use("android.app.ActivityThread$ActivityClientRecord");
    while(it.hasNext()){
      var rec=Java.cast(it.next(), ACR);
      var a=rec.activity.value;
      if(a && !a.isFinishing()){
        if(!rec.paused.value){ found=a; break; }
        if(!found) found=a;
      }
    }
  }catch(e){ S({ev:"at_err", m:String(e).slice(0,120)}); }
  if(found) return found;
  try{
    Java.choose("android.app.Activity", {
      onMatch:function(a){ try{ if(!found && !a.isFinishing()) found=a; }catch(e){} },
      onComplete:function(){}
    });
  }catch(e){ S({ev:"choose_err", m:String(e).slice(0,80)}); }
  return found;
}
function boot(){
 Java.perform(function(){
  try{
   L(null);
   ctxRef=Java.use("android.app.ActivityThread").currentApplication().getApplicationContext();
   var DexClassLoader=Java.use("dalvik.system.DexClassLoader");
   dexLoader=DexClassLoader.$new("/data/local/tmp/module_521.apk",
      ctxRef.getCodeCacheDir().getAbsolutePath(), null, ctxRef.getClassLoader());
   L(dexLoader);
   var BillingClient=Java.use("com.android.billingclient.api.BillingClient");
   var PUL=Java.use("com.android.billingclient.api.PurchasesUpdatedListener");
   var Lst=Java.registerClass({name:"rc.A"+Date.now(), implements:[PUL], methods:{
     onPurchasesUpdated:function(r,p){ S({ev:"purchase_cb", code:r.getResponseCode(), msg:String(r.getDebugMessage()||"")}); }}});
   var b=BillingClient.newBuilder(ctxRef);
   b.setListener(Lst.$new());
   try{ b.enablePendingPurchases(); }catch(e){}
   clientRef=b.build();
   var SLL=Java.use("com.android.billingclient.api.BillingClientStateListener");
   var SL=Java.registerClass({name:"rc.B"+Date.now(), implements:[SLL], methods:{
     onBillingSetupFinished:function(r){ S({ev:"setup", code:r.getResponseCode()});
        if(r.getResponseCode()===0) query(); },
     onBillingServiceDisconnected:function(){ S({ev:"disc"}); }}});
   clientRef.startConnection(SL.$new());
   S({ev:"connecting", products:PRODUCTS});
  }catch(e){ S({ev:"boot_err", m:String(e).slice(0,200)}); }
 });
}
function query(){
 try{
  L(dexLoader);
  var Prod=Java.use("com.android.billingclient.api.QueryProductDetailsParams$Product");
  var Params=Java.use("com.android.billingclient.api.QueryProductDetailsParams");
  var PDL=Java.use("com.android.billingclient.api.ProductDetailsResponseListener");
  var PL=Java.registerClass({name:"rc.C"+Date.now(), implements:[PDL], methods:{
    onProductDetailsResponse:function(res,list){
      S({ev:"pd", code:res.getResponseCode(), n:(list?list.size():0)});
      if(res.getResponseCode()!==0 || !list || list.size()===0) return;
      L(dexLoader);
      var PD=Java.use("com.android.billingclient.api.ProductDetails");
      var SOD=Java.use("com.android.billingclient.api.ProductDetails$SubscriptionOfferDetails");
      var PP=Java.use("com.android.billingclient.api.ProductDetails$PricingPhase");
      var best=null;
      var fallbackPd=null;
      for(var i=0;i<list.size();i++){
        var pd=Java.cast(list.get(i), PD);
        var pid=String(pd.getProductId());
        if(!fallbackPd) fallbackPd=pd;
        var offs=pd.getSubscriptionOfferDetails();
        if(!offs){ S({ev:"no_offers", product:pid}); continue; }
        for(var j=0;j<offs.size();j++){
          var o=Java.cast(offs.get(j), SOD);
          var oid=String(o.getOfferId());
          var tok=String(o.getOfferToken());
          var ph=o.getPricingPhases().getPricingPhaseList();
          var phCount=ph.size();
          var first=Java.cast(ph.get(0), PP);
          var last=Java.cast(ph.get(phCount-1), PP);
          var micros=String(first.getPriceAmountMicros());
          var baseMicros=String(last.getPriceAmountMicros());
          var period=String(first.getBillingPeriod());
          S({ev:"offer", product:pid, id:oid, micros:micros, base_micros:baseMicros, phases:phCount, period:period, token:tok, title:String(pd.getTitle()), name:String(pd.getName())});
          var hasCustomOfferTok=(typeof OFFER_TOKEN!=="undefined" && OFFER_TOKEN);
          var matchPrefer=(PREFER && oid===PREFER) || (hasCustomOfferTok && tok===OFFER_TOKEN);
          var allowDisc=(typeof ALLOW_DISCOUNT!=="undefined" && ALLOW_DISCOUNT);
          var hasOfferId=(oid && oid!=="null");
          var isDiscount=(micros==="0") || (phCount>1 && Number(micros)<Number(baseMicros)) || hasOfferId;
          if(PREFER && !matchPrefer) continue;
          if(!matchPrefer){
            if(allowDisc){
              if(!isDiscount) continue;
            }else if(micros!=="0"){
              continue;
            }
          }
          var rank=periodRank(period);
          var microsNum=Number(micros);
          var better=!best || matchPrefer;
          if(!better && best){
            if(micros==="0" && best.micros!=="0") better=true;
            else if((micros==="0") === (best.micros==="0")){
              if(allowDisc && microsNum<best.microsNum) better=true;
              else if(microsNum===best.microsNum && rank>best.rank) better=true;
            }
          }
          if(better){
            best={pd:pd, offer:o, product:pid, id:oid, rank:rank, period:period, token:tok, micros:micros, microsNum:microsNum};
          }
        }
      }
      if(!best && fallbackPd && typeof OFFER_TOKEN!=="undefined" && OFFER_TOKEN){
        best={pd:fallbackPd, offer:null, product:String(fallbackPd.getProductId()), id:PREFER||"introprice", period:"P1M", token:OFFER_TOKEN};
      }
      if(!best){ S({ev:"no_trial"}); return; }
      S({ev:"chosen", product:best.product, id:best.id, period:best.period});
      if (typeof LIST_ONLY !== "undefined" && LIST_ONLY) {
        S({ev:"list_only", product:best.product, id:best.id, period:best.period, token:best.token});
        return;
      }
      if (typeof OLD_TOKEN !== "undefined" && OLD_TOKEN) {
        S({ev:"stack_start", product:best.product, id:best.id, src:"provided_token"});
        launch(best.pd, best.offer, OLD_TOKEN);
      } else if (typeof STACK !== "undefined" && STACK) {
        S({ev:"stack_start", product:best.product, id:best.id, src:"query"});
        launchWithStack(best.pd, best.offer);
      } else {
        launch(best.pd, best.offer);
      }
    }}});
  var arr=Java.use("java.util.ArrayList").$new();
  for(var k=0;k<PRODUCTS.length;k++){
    arr.add(Prod.newBuilder().setProductId(PRODUCTS[k]).setProductType("subs").build());
  }
  L(dexLoader);
  clientRef.queryProductDetailsAsync(Params.newBuilder().setProductList(arr).build(), PL.$new());
  S({ev:"query_sent"});
 }catch(e){ S({ev:"query_err", m:String(e).slice(0,200)}); }
}
function launchWithStack(pd, offer){
 try{
  L(dexLoader);
  var QP=Java.use("com.android.billingclient.api.QueryPurchasesParams");
  var PRL=Java.use("com.android.billingclient.api.PurchasesResponseListener");
  var cls=Java.registerClass({name:"rc.P"+Date.now(), implements:[PRL], methods:{
    onQueryPurchasesResponse:function(br, purchases){
      try{
        var list=Java.cast(purchases, Java.use("java.util.List"));
        S({ev:"purchases", n:list.size(), code:String(br.getResponseCode())});
        if(list.size()===0){ S({ev:"no_purchase"}); launch(pd, offer); return; }
        var pu=Java.cast(list.get(0), Java.use("com.android.billingclient.api.Purchase"));
        var tok=String(pu.getPurchaseToken());
        S({ev:"old_purchase", head:tok.slice(0,16), products:String(pu.getProducts())});
        launch(pd, offer, tok);
      }catch(e){ S({ev:"stack_query_err", m:String(e).slice(0,200)}); launch(pd, offer); }
    }}});
  var qp=QP.newBuilder().setProductType("subs").build();
  clientRef.queryPurchasesAsync(qp, cls.$new());
 }catch(e){ S({ev:"stack_outer_err", m:String(e).slice(0,200)}); launch(pd, offer); }
}

function launch(pd, offer, oldTok){
 try{
  L(dexLoader);
  var PDP=Java.use("com.android.billingclient.api.BillingFlowParams$ProductDetailsParams");
  var BFP=Java.use("com.android.billingclient.api.BillingFlowParams");
  var offerTok = offer ? String(offer.getOfferToken()) : String(OFFER_TOKEN);
  var pdp=PDP.newBuilder().setProductDetails(pd).setOfferToken(offerTok).build();
  var l=Java.use("java.util.ArrayList").$new(); l.add(pdp);
  var b=BFP.newBuilder().setProductDetailsParamsList(l);
  if(oldTok){
    // Nâng cấp gói đăng ký: purchaseToken cũ + CHARGE_FULL_PRICE(5)
    // Như vậy Play sẽ quy đổi «thời gian dùng thử còn lại» rồi dời lại, thay vì "đổi sang cùng gói, ngày không đổi"
    try{
      var SUP=Java.use("com.android.billingclient.api.BillingFlowParams$SubscriptionUpdateParams");
      var md = (typeof STACK_MODE !== "undefined" && STACK_MODE) ? STACK_MODE : 5;
      var sb=SUP.newBuilder();
      // Phiên bản Billing này dùng setReplaceProrationMode (tên cũ là setReplaceSkusProrationMode)
      var mode_set=false;
      try{ sb=sb.setReplaceProrationMode(md); mode_set=true; }
      catch(e1){
        try{ sb=sb.setReplaceSkusProrationMode(md); mode_set=true; }
        catch(e2){ S({ev:"mode_err", m:String(e2).slice(0,120)}); }
      }
      S({ev:"mode_applied", mode:md, ok:mode_set});
      var sup=sb.setOldPurchaseToken(String(oldTok)).build();
      b=b.setSubscriptionUpdateParams(sup);
      S({ev:"stack_mode", mode:md, old: String(oldTok).slice(0,16)});
    }catch(e){ S({ev:"stack_param_err", m:String(e).slice(0,160)}); }
  }
  var params=b.build();
  var act=getActivity();
  S({ev:"activity", a: act? String(act.getClass().getName()) : "null"});
  if(!act){ S({ev:"no_activity"}); return; }
  L(null);
  var Handler=Java.use("android.os.Handler"); var Looper=Java.use("android.os.Looper");
  var R=Java.registerClass({name:"rc.R"+Date.now(), implements:[Java.use("java.lang.Runnable")], methods:{
    run:function(){
      try{
        L(dexLoader);
        var Activity=Java.use("android.app.Activity");
        var r2=clientRef.launchBillingFlow(Java.cast(act, Activity), params);
        S({ev:"launched", code:r2.getResponseCode(), msg:String(r2.getDebugMessage()||"")});
      }catch(e){ S({ev:"launch_err", m:String(e).slice(0,200)}); }
    }}});
  Handler.$new(Looper.getMainLooper()).post(R.$new());
 }catch(e){ S({ev:"launch_outer_err", m:String(e).slice(0,200)}); }
}
var __tries=0;
var iv=setInterval(function(){
  try{
    L(null);
    var a=Java.use("android.app.ActivityThread").currentApplication();
    __tries++;
    if(a || __tries>10){ clearInterval(iv); S({ev:"boot_start", app:!!a, tries:__tries}); boot(); }
  }catch(e){
    __tries++;
    if(__tries>10){ clearInterval(iv); S({ev:"boot_force", m:String(e).slice(0,120)}); try{ boot(); }catch(e2){ S({ev:"boot_fail", m:String(e2).slice(0,160)}); } }
  }
},400);
