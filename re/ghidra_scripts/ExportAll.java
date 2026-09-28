// Post-script: dump decompiled C + disassembly listing for every function
import ghidra.app.script.GhidraScript;
import ghidra.app.decompiler.*;
import ghidra.program.model.listing.*;
import java.io.*;

public class ExportAll extends GhidraScript {
    @Override
    public void run() throws Exception {
        String out = getScriptArgs()[0];
        DecompInterface di = new DecompInterface();
        DecompileOptions opts = new DecompileOptions();
        opts.grabFromProgram(currentProgram);
        opts.setRespectReadOnly(true);
        di.setOptions(opts);
        di.openProgram(currentProgram);
        try (PrintWriter c = new PrintWriter(new FileWriter(out + ".c"));
             PrintWriter l = new PrintWriter(new FileWriter(out + ".lst"))) {
            for (Function f : currentProgram.getFunctionManager().getFunctions(true)) {
                DecompileResults r = di.decompileFunction(f, 60, monitor);
                c.println("// ==== " + f.getName() + " @ " + f.getEntryPoint());
                if (r != null && r.decompileCompleted()) c.println(r.getDecompiledFunction().getC());
                else c.println("// decompile failed");
            }
            for (Instruction ins : currentProgram.getListing().getInstructions(currentProgram.getMemory(), true)) {
                Function f = currentProgram.getFunctionManager().getFunctionContaining(ins.getAddress());
                l.println(ins.getAddress() + "\t" + (f == null ? "-" : f.getName()) + "\t" + ins.toString());
            }
        }
        println("functions: " + currentProgram.getFunctionManager().getFunctionCount());
    }
}
