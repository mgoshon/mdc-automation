using System;
using System.IO;
using System.Text.Json;
using System.Text.RegularExpressions;

namespace MDC.Automation
{
    /// <summary>Inputs passed in as params.json by the work item. All dimensions are in inches.</summary>
    public class BoxParams
    {
        public double WidthIn { get; set; } = 24;
        public double DepthIn { get; set; } = 24;
        public double HeightIn { get; set; } = 36;
        public string TypeName { get; set; } = "Standard";

        private const double MinIn = 1;
        private const double MaxIn = 240;

        public static BoxParams Load(string path)
        {
            if (!File.Exists(path))
                throw new FileNotFoundException("params.json was not provided to the work item.", path);

            var options = new JsonSerializerOptions { PropertyNameCaseInsensitive = true };
            var p = JsonSerializer.Deserialize<BoxParams>(File.ReadAllText(path), options);
            if (p == null) throw new InvalidDataException("params.json could not be parsed.");
            p.Validate();
            return p;
        }

        public void Validate()
        {
            CheckRange(nameof(WidthIn), WidthIn);
            CheckRange(nameof(DepthIn), DepthIn);
            CheckRange(nameof(HeightIn), HeightIn);

            // Keep type names simple and safe for Revit.
            TypeName = Regex.Replace(TypeName ?? "", @"[^A-Za-z0-9 _\-]", "").Trim();
            if (TypeName.Length == 0) TypeName = "Standard";
            if (TypeName.Length > 60) TypeName = TypeName.Substring(0, 60);
        }

        private static void CheckRange(string name, double value)
        {
            if (double.IsNaN(value) || value < MinIn || value > MaxIn)
                throw new ArgumentOutOfRangeException(name, $"{name} must be between {MinIn} and {MaxIn} inches (got {value}).");
        }

        // Revit's internal length unit is decimal feet.
        public double WidthFt => WidthIn / 12.0;
        public double DepthFt => DepthIn / 12.0;
        public double HeightFt => HeightIn / 12.0;
    }
}
