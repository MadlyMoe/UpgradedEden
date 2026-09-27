// EXPERIMENTAL: speed improved, but process exits occurred in this environment.
// Prefer android_preseed.py. Retained as investigation evidence, not a stable patch.
// Temporary, process-local tuning for the isolated 3.17.0 / 699 client.
// Load with the installed Frida CLI (which supplies its Java bridge).
// No URL, TLS, integrity, account, gameplay, or manifest hooks.
const downloadConnections = 24;

Java.perform(function () {
    const app = Java.use('android.app.ActivityThread').currentApplication();
    const pkg = app.getPackageName().toString();
    const info = app.getPackageManager().getPackageInfo(pkg, 0);
    if (pkg !== 'games.wfs.anothereden' || info.versionCode.value !== 699 ||
        info.versionName.value.toString() !== '3.17.0') {
        throw new Error('Unexpected client; downloader unchanged');
    }
    const Downloader = Java.use('net.wrightflyer.cocos2dx.network.Cocos2dxDownloader');
    const Http = Java.use('com.loopj.android.http.AsyncHttpClient');
    const Pool = Java.use('cz.msebera.android.httpclient.impl.conn.tsccm.ThreadSafeClientConnManager');
    const Backend = Java.use('cz.msebera.android.httpclient.impl.conn.tsccm.ConnPoolByRoute');
    const RouteLimits = Java.use('cz.msebera.android.httpclient.conn.params.ConnPerRouteBean');
    const Queue = Java.use('java.util.LinkedList');
    const configured = new Set();
    function tune(d) {
        const id = d.mId.value;
        if (configured.has(id)) return;
        const h = Java.cast(d.mHttpClient.value, Http);
        const pool = Java.cast(h.getHttpClient().getConnectionManager(), Pool);
        // The deprecated manager constructor keeps a different route-limit
        // object in its backend. Its public default getter is misleading.
        const routes = Java.cast(Java.cast(pool.pool.value, Backend).connPerRoute.value, RouteLimits);
        const before = {id, tasks: d.mMaxConnections.value, http: h.maxConnections.value,
            total: pool.getMaxTotal(), perRoute: routes.getDefaultMaxPerRoute()};
        d.mMaxConnections.value = downloadConnections;
        h.setMaxConnections(downloadConnections);
        pool.setMaxTotal(downloadConnections);
        pool.setDefaultMaxPerRoute(downloadConnections);
        routes.setDefaultMaxPerRoute(downloadConnections);
        if (d.mMaxConnections.value !== downloadConnections ||
            pool.getMaxTotal() !== downloadConnections ||
            routes.getDefaultMaxPerRoute() !== downloadConnections) {
            throw new Error('Downloader tuning readback failed');
        }
        configured.add(id);
        send({before, after: downloadConnections});
    }
    // Confirmation recreates the phase downloaders and native code reapplies
    // its limit. Keep only these two downloader-specific hooks until exit.
    const setLimit = Downloader.setMaxConnections.overload('int');
    setLimit.implementation = function () { setLimit.call(this, downloadConnections); };
    const start = Downloader.startTask.overload('net.wrightflyer.cocos2dx.network.DownloadTask');
    start.implementation = function (task) { tune(this); start.call(this, task); };
    const instances = [];
    Java.choose(Downloader.$className, {
        onMatch: function (d) { instances.push(Java.retain(d)); },
        onComplete: function () {
            Java.scheduleOnMainThread(function () {
                // Existing tasks retain their original callbacks and queue.
                // A newly submitted task fills any extra available slots.
                instances.forEach(function (ref) {
                    const d = Java.cast(ref, Downloader);
                    tune(d);
                    const queue = Java.cast(d.mTaskQueue.value, Queue);
                    if (!d.mIsSuspended.value) {
                        Java.synchronized(queue, function () {
                            // Increasing a limit does not fill an already
                            // queued batch: stock completion only replaces one.
                            while (queue.size() > 0 && d.mRunningTaskCount.value < downloadConnections) {
                                d.mRunningTaskCount.value++;
                                d.runNextTaskIfExists();
                            }
                        });
                    }
                });
                send({tuned: instances.length, connections: downloadConnections});
            });
        }
    });
});
