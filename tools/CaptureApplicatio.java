package net.wrightflyer.toybox;

import android.content.Context;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.content.pm.Signature;
import java.io.ByteArrayOutputStream;
import java.io.InputStream;
import java.lang.reflect.Field;
import java.lang.reflect.InvocationHandler;
import java.lang.reflect.Method;
import java.lang.reflect.Proxy;

/** Capture-only copy of the supplied mod's local legacy-signature substitution. */
public final class CaptureApplicatio extends ToyboxApplication implements InvocationHandler {
    private Object packageManager;
    private Signature publisherSignature;
    private String packageName;

    @Override protected void attachBaseContext(Context context) {
        try {
            ByteArrayOutputStream certificate = new ByteArrayOutputStream();
            try (InputStream input = context.getAssets().open("forevereden-publisher.der")) {
                byte[] chunk = new byte[4096];
                for (int read; (read = input.read(chunk)) != -1;) certificate.write(chunk, 0, read);
            }
            publisherSignature = new Signature(certificate.toByteArray());
            packageName = context.getPackageName();
            Class<?> activityThread = Class.forName("android.app.ActivityThread");
            Object thread = activityThread.getDeclaredMethod("currentActivityThread").invoke(null);
            Field service = activityThread.getDeclaredField("sPackageManager");
            service.setAccessible(true);
            packageManager = service.get(thread);
            Class<?> contract = Class.forName("android.content.pm.IPackageManager");
            Object proxy = Proxy.newProxyInstance(contract.getClassLoader(), new Class<?>[]{contract}, this);
            service.set(thread, proxy);
            PackageManager local = context.getPackageManager();
            Field localService = local.getClass().getDeclaredField("mPM");
            localService.setAccessible(true);
            localService.set(local, proxy);
        } catch (Exception error) {
            throw new IllegalStateException("Capture signature isolation failed", error);
        }
        super.attachBaseContext(context);
    }

    @Override public Object invoke(Object proxy, Method method, Object[] arguments) throws Throwable {
        Object result = method.invoke(packageManager, arguments);
        if (method.getName().equals("getPackageInfo") && arguments.length >= 2 &&
                arguments[0] instanceof String && arguments[0].equals(packageName) &&
                arguments[1] instanceof Number && ((((Number) arguments[1]).longValue() & 64) != 0)) {
            ((PackageInfo) result).signatures = new Signature[]{publisherSignature};
        }
        return result;
    }
}
