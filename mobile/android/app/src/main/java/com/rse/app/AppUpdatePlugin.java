package com.rse.app;

import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;

import androidx.core.content.FileProvider;

import com.getcapacitor.JSObject;
import com.getcapacitor.Plugin;
import com.getcapacitor.PluginCall;
import com.getcapacitor.PluginMethod;
import com.getcapacitor.annotation.CapacitorPlugin;

import java.io.BufferedInputStream;
import java.io.File;
import java.io.FileOutputStream;
import java.io.InputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.security.MessageDigest;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/**
 * In-app APK self-update for sideloaded builds.
 * Downloads an APK and launches the system package installer.
 * Stock Android always shows a system Install confirmation dialog.
 */
@CapacitorPlugin(name = "AppUpdate")
public class AppUpdatePlugin extends Plugin {

    private final ExecutorService executor = Executors.newSingleThreadExecutor();

    @PluginMethod
    public void getInfo(PluginCall call) {
        try {
            PackageManager pm = getContext().getPackageManager();
            String pkg = getContext().getPackageName();
            PackageInfo pi = pm.getPackageInfo(pkg, 0);
            JSObject ret = new JSObject();
            ret.put("packageName", pkg);
            ret.put("versionName", pi.versionName != null ? pi.versionName : "");
            long code;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.P) {
                code = pi.getLongVersionCode();
            } else {
                code = pi.versionCode;
            }
            ret.put("versionCode", code);
            ret.put("platform", "android");
            // Play-installed builds must not self-update via sideload APKs (Play policy).
            ret.put("fromPlayStore", isInstalledFromPlay(pm, pkg));
            call.resolve(ret);
        } catch (Exception e) {
            call.reject("Failed to read app version: " + e.getMessage());
        }
    }

    private boolean isInstalledFromPlay(PackageManager pm, String pkg) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
                String installer = pm.getInstallSourceInfo(pkg).getInstallingPackageName();
                return "com.android.vending".equals(installer)
                        || "com.google.android.feedback".equals(installer);
            }
            //noinspection deprecation
            String installer = pm.getInstallerPackageName(pkg);
            return "com.android.vending".equals(installer);
        } catch (Exception e) {
            return false;
        }
    }

    @PluginMethod
    public void canInstallPackages(PluginCall call) {
        JSObject ret = new JSObject();
        boolean allowed = true;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            allowed = getContext().getPackageManager().canRequestPackageInstalls();
        }
        ret.put("allowed", allowed);
        call.resolve(ret);
    }

    @PluginMethod
    public void openInstallPermissionSettings(PluginCall call) {
        try {
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                Intent intent = new Intent(Settings.ACTION_MANAGE_UNKNOWN_APP_SOURCES);
                intent.setData(Uri.parse("package:" + getContext().getPackageName()));
                intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
                getContext().startActivity(intent);
            }
            call.resolve();
        } catch (Exception e) {
            call.reject("Could not open install permission settings: " + e.getMessage());
        }
    }

    @PluginMethod
    public void downloadAndInstall(PluginCall call) {
        final String apkUrl = call.getString("url");
        if (apkUrl == null || apkUrl.trim().isEmpty()) {
            call.reject("url required");
            return;
        }
        final String expectedSha = call.getString("sha256", null);

        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            if (!getContext().getPackageManager().canRequestPackageInstalls()) {
                JSObject ret = new JSObject();
                ret.put("started", false);
                ret.put("needsPermission", true);
                ret.put("message", "Allow installs from The RSE, then the update will continue.");
                call.resolve(ret);
                return;
            }
        }

        final String urlFinal = apkUrl.trim();
        executor.execute(() -> downloadAndLaunch(call, urlFinal, expectedSha));
    }

    private void downloadAndLaunch(PluginCall call, String apkUrl, String expectedSha) {
        HttpURLConnection conn = null;
        File outFile = null;
        try {
            File dir = new File(getContext().getCacheDir(), "updates");
            if (!dir.exists() && !dir.mkdirs()) {
                rejectOnMain(call, "Could not create update cache directory");
                return;
            }
            outFile = new File(dir, "rse-update.apk");

            URL url = new URL(apkUrl);
            conn = (HttpURLConnection) url.openConnection();
            conn.setConnectTimeout(30000);
            conn.setReadTimeout(180000);
            conn.setInstanceFollowRedirects(true);
            conn.setRequestProperty("User-Agent", "TheRSE-AppUpdate/1.0");
            conn.connect();

            int status = conn.getResponseCode();
            if (status == HttpURLConnection.HTTP_MOVED_TEMP
                    || status == HttpURLConnection.HTTP_MOVED_PERM
                    || status == 307 || status == 308) {
                String loc = conn.getHeaderField("Location");
                conn.disconnect();
                conn = (HttpURLConnection) new URL(loc).openConnection();
                conn.setConnectTimeout(30000);
                conn.setReadTimeout(180000);
                conn.setRequestProperty("User-Agent", "TheRSE-AppUpdate/1.0");
                conn.connect();
                status = conn.getResponseCode();
            }
            if (status < 200 || status >= 300) {
                rejectOnMain(call, "Download failed (HTTP " + status + ")");
                return;
            }

            long total = conn.getContentLengthLong();
            MessageDigest digest = null;
            if (expectedSha != null && !expectedSha.trim().isEmpty()) {
                digest = MessageDigest.getInstance("SHA-256");
            }

            try (InputStream in = new BufferedInputStream(conn.getInputStream());
                 FileOutputStream out = new FileOutputStream(outFile)) {
                byte[] buf = new byte[8192];
                long readTotal = 0;
                int n;
                int lastPct = -1;
                while ((n = in.read(buf)) != -1) {
                    out.write(buf, 0, n);
                    if (digest != null) {
                        digest.update(buf, 0, n);
                    }
                    readTotal += n;
                    if (total > 0) {
                        int pct = (int) ((readTotal * 100L) / total);
                        if (pct != lastPct && (pct % 5 == 0 || pct >= 99)) {
                            lastPct = pct;
                            final int report = Math.min(pct, 100);
                            final long rt = readTotal;
                            final long tot = total;
                            getActivity().runOnUiThread(() -> {
                                JSObject progress = new JSObject();
                                progress.put("percent", report);
                                progress.put("bytes", rt);
                                progress.put("total", tot);
                                notifyListeners("downloadProgress", progress);
                            });
                        }
                    }
                }
                out.flush();
            }

            if (digest != null) {
                String actual = toHex(digest.digest());
                if (!actual.equalsIgnoreCase(expectedSha.trim())) {
                    //noinspection ResultOfMethodCallIgnored
                    outFile.delete();
                    rejectOnMain(call, "APK checksum mismatch");
                    return;
                }
            }

            if (outFile.length() < 1024L) {
                //noinspection ResultOfMethodCallIgnored
                outFile.delete();
                rejectOnMain(call, "Downloaded file is too small to be an APK");
                return;
            }

            final File apk = outFile;
            getActivity().runOnUiThread(() -> {
                try {
                    launchInstaller(apk);
                    JSObject ok = new JSObject();
                    ok.put("started", true);
                    ok.put("needsPermission", false);
                    ok.put("path", apk.getAbsolutePath());
                    call.resolve(ok);
                } catch (Exception e) {
                    call.reject("Install launch failed: " + e.getMessage());
                }
            });
        } catch (Exception e) {
            if (outFile != null) {
                //noinspection ResultOfMethodCallIgnored
                outFile.delete();
            }
            rejectOnMain(call, "Update download failed: " + e.getMessage());
        } finally {
            if (conn != null) {
                conn.disconnect();
            }
        }
    }

    private void rejectOnMain(PluginCall call, String message) {
        getActivity().runOnUiThread(() -> call.reject(message));
    }

    private void launchInstaller(File apkFile) {
        Uri uri = FileProvider.getUriForFile(
                getContext(),
                getContext().getPackageName() + ".fileprovider",
                apkFile
        );
        Intent intent = new Intent(Intent.ACTION_VIEW);
        intent.setDataAndType(uri, "application/vnd.android.package-archive");
        intent.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
        getContext().startActivity(intent);
    }

    private static String toHex(byte[] bytes) {
        StringBuilder sb = new StringBuilder(bytes.length * 2);
        for (byte b : bytes) {
            sb.append(String.format("%02x", b));
        }
        return sb.toString();
    }
}
