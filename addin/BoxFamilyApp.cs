using System;
using System.IO;
using Autodesk.Revit.ApplicationServices;
using Autodesk.Revit.DB;
using DesignAutomationFramework;

namespace MDC.Automation
{
    /// <summary>
    /// Entry point for the cloud Revit engine. There is no UI in the cloud, so this is an
    /// IExternalDBApplication that waits for DesignAutomationReadyEvent and then runs.
    /// Working directory contents (set by the Activity):
    ///   template.rft  (input)   Generic Model family template
    ///   params.json   (input)   BoxParams
    ///   result.rfa    (output)  generated family
    /// </summary>
    public class BoxFamilyApp : IExternalDBApplication
    {
        public ExternalDBApplicationResult OnStartup(ControlledApplication app)
        {
            DesignAutomationBridge.DesignAutomationReadyEvent += OnDesignAutomationReady;
            return ExternalDBApplicationResult.Succeeded;
        }

        public ExternalDBApplicationResult OnShutdown(ControlledApplication app)
        {
            return ExternalDBApplicationResult.Succeeded;
        }

        private void OnDesignAutomationReady(object sender, DesignAutomationReadyEventArgs e)
        {
            e.Succeeded = true;
            try
            {
                DesignAutomationData data = e.DesignAutomationData;
                Run(data.RevitApp, ResolveWorkDir(data));
            }
            catch (Exception ex)
            {
                // Anything written to the console shows up in the work item report.
                Console.WriteLine("MDC ERROR: " + ex);
                e.Succeeded = false;
            }
        }

        /// <summary>
        /// Cloud: inputs sit in the current working directory.
        /// Local debug (AutomationServiceHandler in desktop Revit): the current directory is usually
        /// Revit's install folder, so fall back to the folder of the opened host .rvt, then to the
        /// MDC_WORKDIR environment variable.
        /// </summary>
        private static string ResolveWorkDir(DesignAutomationData data)
        {
            var candidates = new[]
            {
                Directory.GetCurrentDirectory(),
                string.IsNullOrEmpty(data?.FilePath) ? null : Path.GetDirectoryName(data.FilePath),
                Environment.GetEnvironmentVariable("MDC_WORKDIR"),
            };

            foreach (string dir in candidates)
            {
                if (!string.IsNullOrEmpty(dir) && File.Exists(Path.Combine(dir, "params.json")))
                {
                    Console.WriteLine("MDC: working folder " + dir);
                    return dir;
                }
            }
            throw new FileNotFoundException(
                "params.json not found in the working directory, the host model folder, or MDC_WORKDIR.");
        }

        private static void Run(Application app, string workDir)
        {
            string templatePath = Path.Combine(workDir, "template.rft");
            string paramsPath = Path.Combine(workDir, "params.json");
            string resultPath = Path.Combine(workDir, "result.rfa");

            BoxParams p = BoxParams.Load(paramsPath);
            Console.WriteLine($"MDC: building box {p.WidthIn} x {p.DepthIn} x {p.HeightIn} in, type '{p.TypeName}'");

            if (!File.Exists(templatePath))
                throw new FileNotFoundException("template.rft was not provided to the work item.", templatePath);

            Document famDoc = app.NewFamilyDocument(templatePath);
            if (famDoc == null || !famDoc.IsFamilyDocument)
                throw new InvalidOperationException("Could not create a family document from template.rft.");

            BoxBuilder.Build(famDoc, p);

            var saveOptions = new SaveAsOptions { OverwriteExistingFile = true };
            famDoc.SaveAs(resultPath, saveOptions);
            famDoc.Close(false);

            Console.WriteLine("MDC: saved " + resultPath);
        }
    }
}
